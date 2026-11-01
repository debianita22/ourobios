/* tpm-pcr-test.c: the PCRs of the TPM, reported on COM1 (the step 11 of
 * tools/qemu-smoke.py, tools/build.sh smoke).
 *
 * The payload boots this application as \EFI\BOOT\BOOTX64.EFI from an ESP,
 * after ReadyToBoot: the event log then holds coreboot's measurements, the
 * payload's and the separators. PCR 0 to 7 are read from the TPM through the
 * protocol of the payload's TPM driver, EFI_TCG2_PROTOCOL (TPM 2.0, the SHA-1
 * and SHA-256 banks; with the address of its crypto agile log, from
 * GetEventLog()) or EFI_TCG_PROTOCOL (TPM 1.2, SHA-1), and printed for the
 * harness to replay the log against; "RESULT OK" closes, then the application
 * waits, for the harness to read the RAM with the log. No library: clang
 * --target=x86_64-unknown-windows, as the other applications of tools/efi.
 */
#include <stdint.h>
#include <stddef.h>

#define COM1 0x3f8
#define MARK "ouroBIOS tpm test: "

typedef uint64_t efi_status;
#define EFI_ERR(s) ((s) >> 63)

struct guid { uint32_t a; uint16_t b, c; uint8_t d[8]; };
struct table_header { uint64_t signature; uint32_t revision, header_size, crc32, reserved; };
struct boot_services {
	struct table_header hdr;
	void *fn[37];
	efi_status (*locate_protocol)(struct guid *protocol, void *registration, void **interface);
};
struct system_table {
	struct table_header hdr;
	uint16_t *firmware_vendor;
	uint32_t firmware_revision;
	void *console_in_handle, *con_in, *console_out_handle, *con_out, *standard_error_handle, *std_err;
	void *rt;
	struct boot_services *bs;
};
_Static_assert(offsetof(struct boot_services, locate_protocol) == 0x140, "LocateProtocol");

/* SecurityPkg/Include/Protocol/TcgService.h and Tcg2Protocol.h: the
 * functions before the one used here */
struct tcg_protocol {
	void *status_check, *hash_all, *log_event;
	efi_status (*pass_through_to_tpm)(struct tcg_protocol *this, uint32_t in_size, uint8_t *in,
					  uint32_t out_size, uint8_t *out);
};
struct tcg2_protocol {
	void *get_capability;
	efi_status (*get_event_log)(struct tcg2_protocol *this, uint32_t format, uint64_t *location,
				    uint64_t *last_entry, uint8_t *truncated);
	void *hash_log_extend_event;
	efi_status (*submit_command)(struct tcg2_protocol *this, uint32_t in_size, uint8_t *in,
				     uint32_t out_size, uint8_t *out);
};
static struct guid tcg_guid = { 0xf541796d, 0xa62e, 0x4954, { 0xa7, 0x75, 0x95, 0x84, 0xf6, 0x1b, 0x9c, 0xdd } };
static struct guid tcg2_guid = { 0x607f766c, 0x7455, 0x42be, { 0x93, 0x0b, 0xe4, 0xd7, 0x6d, 0xb2, 0x72, 0x0f } };

static inline uint8_t inb(uint16_t port) { uint8_t v; __asm__ volatile("inb %1, %0" : "=a"(v) : "Nd"(port)); return v; }
static inline void outb(uint16_t port, uint8_t v) { __asm__ volatile("outb %0, %1" : : "a"(v), "Nd"(port)); }
static void putc_(char c) { int i; for (i = 0; i < 100000 && !(inb(COM1 + 5) & 0x20); i++) { } outb(COM1, (uint8_t)c); }
static void puts_(const char *s) { for (; *s; s++) { if (*s == '\n') putc_('\r'); putc_(*s); } }
static void puthex(uint64_t v, int digits) { int s; for (s = (digits - 1) * 4; s >= 0; s -= 4) putc_("0123456789abcdef"[(v >> s) & 0xf]); }
static void putdec(uint64_t v) { char b[21]; int i = 20; b[i] = 0; do { b[--i] = (char)('0' + v % 10); v /= 10; } while (v); puts_(b + i); }

static void be16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static void be32(uint8_t *p, uint32_t v) { be16(p, (uint16_t)(v >> 16)); be16(p + 2, (uint16_t)v); }
static uint32_t rd32(const uint8_t *p) { return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3]; }

static void put_pcr(unsigned int pcr, const char *bank, const uint8_t *digest, int size)
{
	int i;
	puts_(MARK "pcr "); putdec(pcr); puts_(" "); puts_(bank); puts_(" ");
	for (i = 0; i < size; i++) puthex(digest[i], 2);
	puts_("\n");
}

static void fail(const char *what, unsigned int pcr, efi_status s, uint32_t rc)
{
	puts_(MARK "FAIL "); puts_(what); puts_(" pcr "); putdec(pcr);
	puts_(" status 0x"); puthex(s, 16); puts_(" rc 0x"); puthex(rc, 8); puts_("\n");
}

/* TPM2_PCR_Read of one PCR of a bank: the response has the update counter,
 * the selection read (10 bytes), the count of digests and the first
 * TPM2B_DIGEST at 28 */
static int tpm2_pcrs(struct tcg2_protocol *tcg2, uint16_t alg, const char *bank, uint8_t size)
{
	unsigned int pcr;
	for (pcr = 0; pcr < 8; pcr++) {
		uint8_t in[20] = { 0 }, out[64] = { 0 };
		efi_status s;
		be16(in, 0x8001);		/* TPM_ST_NO_SESSIONS */
		be32(in + 2, sizeof(in));
		be32(in + 6, 0x17e);		/* TPM_CC_PCR_Read */
		be32(in + 10, 1);		/* one TPMS_PCR_SELECTION */
		be16(in + 14, alg);
		in[16] = 3;			/* sizeofSelect */
		in[17 + pcr / 8] = (uint8_t)(1u << (pcr % 8));
		s = tcg2->submit_command(tcg2, sizeof(in), in, sizeof(out), out);
		if (EFI_ERR(s) || rd32(out + 6) != 0 || rd32(out + 24) != 1 || out[28] != 0 || out[29] != size) {
			fail("TPM2_PCR_Read", pcr, s, rd32(out + 6));
			return 0;
		}
		put_pcr(pcr, bank, out + 30, size);
	}
	return 1;
}

/* TPM_PCRRead: the digest follows the 10 bytes of the response header */
static int tpm1_pcrs(struct tcg_protocol *tcg)
{
	unsigned int pcr;
	for (pcr = 0; pcr < 8; pcr++) {
		uint8_t in[14] = { 0 }, out[30] = { 0 };
		efi_status s;
		be16(in, 0x00c1);		/* TPM_TAG_RQU_COMMAND */
		be32(in + 2, sizeof(in));
		be32(in + 6, 0x15);		/* TPM_ORD_PcrRead */
		be32(in + 10, pcr);
		s = tcg->pass_through_to_tpm(tcg, sizeof(in), in, sizeof(out), out);
		if (EFI_ERR(s) || rd32(out + 6) != 0) {
			fail("TPM_PCRRead", pcr, s, rd32(out + 6));
			return 0;
		}
		put_pcr(pcr, "sha1", out + 10, 20);
	}
	return 1;
}

__attribute__((ms_abi)) efi_status efi_main(void *image, struct system_table *st)
{
	struct tcg2_protocol *tcg2 = 0;
	struct tcg_protocol *tcg = 0;
	int ok;
	(void)image;

	puts_("\n");
	if (!EFI_ERR(st->bs->locate_protocol(&tcg2_guid, 0, (void **)&tcg2)) && tcg2) {
		uint64_t location = 0, last = 0;
		uint8_t truncated = 0;
		efi_status s;
		puts_(MARK "tpm 2.0\n");
		/* EFI_TCG2_EVENT_LOG_FORMAT_TCG_2 */
		s = tcg2->get_event_log(tcg2, 2, &location, &last, &truncated);
		if (EFI_ERR(s)) {
			fail("GetEventLog", 0, s, 0);
			ok = 0;
		} else {
			puts_(MARK "log 0x"); puthex(location, 16); puts_(" last 0x"); puthex(last, 16);
			puts_(" truncated "); putdec(truncated); puts_("\n");
			ok = tpm2_pcrs(tcg2, 0x0004, "sha1", 20) && tpm2_pcrs(tcg2, 0x000b, "sha256", 32);
		}
	} else if (!EFI_ERR(st->bs->locate_protocol(&tcg_guid, 0, (void **)&tcg)) && tcg) {
		puts_(MARK "tpm 1.2\n");
		ok = tpm1_pcrs(tcg);
	} else {
		puts_(MARK "FAIL no EFI_TCG2_PROTOCOL or EFI_TCG_PROTOCOL\n");
		ok = 0;
	}
	puts_(ok ? MARK "RESULT OK\n" : MARK "RESULT FAIL\n");
	for (;;)
		__asm__ volatile("pause");
}

/* setvar.c: one UEFI variable written through SetVariable(), reported on COM1
 * (the steps 6-8 of tools/qemu-smoke.py, tools/build.sh smoke): what the setvar
 * command of the UEFI Shell did there before the payload of the boards left
 * the Shell out (EDK2_HAVE_EFI_SHELL off, patches/edk2/0053).
 *
 * The payload boots this application as \EFI\BOOT\BOOTX64.EFI from an ESP.
 * The variable comes from QEMU, in the fw_cfg file opt/ourobios/setvar
 * (-fw_cfg name=opt/ourobios/setvar,string=...): its name, its vendor GUID as
 * the 16 bytes in memory order and its data, the last two in hex, separated
 * by a space. It is written non-volatile with boot service and runtime access
 * (NV+BS+RT, as setvar -nv -bs -rt) and read back: the attributes and the data
 * must be those written. "RESULT OK" closes, then the application waits for
 * the harness to find the variable in the flash and power off; back in the
 * boot manager, the next boot option would start. No library: clang
 * --target=x86_64-unknown-windows, as the other applications of tools/efi.
 */
#include <stdint.h>
#include <stddef.h>

#define COM1 0x3f8
#define MARK "ouroBIOS setvar: "

/* QEMU's fw_cfg on x86 (docs/specs/fw_cfg.rst of QEMU): the selector, 16 bits
 * little endian, and the data port, read a byte at a time. Item 0 holds
 * "QEMU", item 0x19 the directory of the named files: a count, then 64 bytes
 * per file, the size, the selector and the name, the numbers big endian */
#define FW_CFG_SELECTOR 0x510
#define FW_CFG_DATA 0x511
#define FW_CFG_SIGNATURE 0x0000
#define FW_CFG_FILE_DIR 0x0019
#define FW_CFG_FILE "opt/ourobios/setvar"

#define NAME_MAX 64
#define DATA_MAX 256

typedef uint64_t efi_status;
#define EFI_ERR(s) ((s) >> 63)
#define EFI_SUCCESS 0

#define ATTR_NV 1u
#define ATTR_BS 2u
#define ATTR_RT 4u

struct guid { uint32_t a; uint16_t b, c; uint8_t d[8]; };
struct table_header { uint64_t signature; uint32_t revision, header_size, crc32, reserved; };
struct runtime_services {
	struct table_header hdr;
	void *get_time, *set_time, *get_wakeup_time, *set_wakeup_time, *set_virtual_address_map, *convert_pointer;
	efi_status (*get_variable)(uint16_t *name, struct guid *vendor, uint32_t *attributes,
				   uint64_t *size, void *data);
	void *get_next_variable_name;
	efi_status (*set_variable)(uint16_t *name, struct guid *vendor, uint32_t attributes,
				   uint64_t size, void *data);
};
struct system_table {
	struct table_header hdr;
	uint16_t *firmware_vendor;
	uint32_t firmware_revision;
	void *console_in_handle, *con_in, *console_out_handle, *con_out, *standard_error_handle, *std_err;
	struct runtime_services *rt;
	void *bs;
};
_Static_assert(offsetof(struct system_table, rt) == 0x58, "RuntimeServices");
_Static_assert(offsetof(struct runtime_services, get_variable) == 0x48, "GetVariable");
_Static_assert(offsetof(struct runtime_services, set_variable) == 0x58, "SetVariable");

static inline void outb(uint16_t port, uint8_t v) { __asm__ volatile("outb %0, %1" : : "a"(v), "Nd"(port)); }
static inline void outw(uint16_t port, uint16_t v) { __asm__ volatile("outw %0, %1" : : "a"(v), "Nd"(port)); }
static inline uint8_t inb(uint16_t port) { uint8_t v; __asm__ volatile("inb %1, %0" : "=a"(v) : "Nd"(port)); return v; }
static void putc_(char c) { int i; for (i = 0; i < 100000 && !(inb(COM1 + 5) & 0x20); i++) { } outb(COM1, (uint8_t)c); }
static void puts_(const char *s) { for (; *s; s++) { if (*s == '\n') putc_('\r'); putc_(*s); } }
static void puthex(uint64_t v, int digits) { int s; for (s = (digits - 1) * 4; s >= 0; s -= 4) putc_("0123456789abcdef"[(v >> s) & 0xf]); }
static void putdec(uint64_t v) { char b[21]; int i = 20; b[i] = 0; do { b[--i] = (char)('0' + v % 10); v /= 10; } while (v); puts_(b + i); }
static void status_name(efi_status s)
{
	if (s == EFI_SUCCESS) puts_("SUCCESS");
	else { puts_("0x"); puthex(s, 16); }
}

static void fw_cfg_read(void *buf, uint32_t size)
{
	uint8_t *p = buf;
	while (size--)
		*p++ = inb(FW_CFG_DATA);
}

static uint32_t be32(const uint8_t *p)
{
	return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}

/* The fw_cfg file name into buf, NUL terminated: its size, or -1 without
 * fw_cfg, without such a file or with a file of max bytes or more */
static int64_t fw_cfg_file(const char *name, char *buf, uint32_t max)
{
	uint8_t sig[4], count[4], entry[64];
	uint32_t n, i, size;
	int k;

	outw(FW_CFG_SELECTOR, FW_CFG_SIGNATURE);
	fw_cfg_read(sig, sizeof(sig));
	if (sig[0] != 'Q' || sig[1] != 'E' || sig[2] != 'M' || sig[3] != 'U')
		return -1;
	outw(FW_CFG_SELECTOR, FW_CFG_FILE_DIR);
	fw_cfg_read(count, sizeof(count));
	n = be32(count);
	for (i = 0; i < n; i++) {
		fw_cfg_read(entry, sizeof(entry));
		for (k = 0; name[k] && entry[8 + k] == (uint8_t)name[k]; k++)
			;
		if (name[k] || entry[8 + k])
			continue;
		size = be32(entry);
		if (size >= max)
			return -1;
		outw(FW_CFG_SELECTOR, (uint16_t)(entry[4] << 8 | entry[5]));
		fw_cfg_read(buf, size);
		buf[size] = 0;
		return size;
	}
	return -1;
}

static int hexval(char c)
{
	if (c >= '0' && c <= '9') return c - '0';
	if (c >= 'a' && c <= 'f') return c - 'a' + 10;
	if (c >= 'A' && c <= 'F') return c - 'A' + 10;
	return -1;
}

/* The hex digits at *p, up to a space or the end, into out: the number of
 * bytes, or -1 for an odd count, another character or more than max bytes */
static int64_t hex_bytes(const char **p, uint8_t *out, uint32_t max)
{
	uint32_t n = 0;
	int hi, lo;

	while (**p && **p != ' ') {
		hi = hexval((*p)[0]);
		lo = hi < 0 ? -1 : hexval((*p)[1]);
		if (lo < 0 || n == max)
			return -1;
		out[n++] = (uint8_t)(hi << 4 | lo);
		*p += 2;
	}
	return n;
}

__attribute__((ms_abi)) efi_status efi_main(void *image, struct system_table *st)
{
	static char text[NAME_MAX + 1 + 32 + 1 + 2 * DATA_MAX + 1];
	static uint16_t name[NAME_MAX + 1];
	static uint8_t data[DATA_MAX], back[DATA_MAX];
	struct guid vendor;
	const char *p = text;
	uint64_t size, back_size, k;
	uint32_t attr = 0;
	int64_t n;
	efi_status s;
	int i, ok = 0;
	(void)image;

	puts_("\n");
	if (fw_cfg_file(FW_CFG_FILE, text, sizeof(text)) < 0) {
		puts_(MARK "FAIL no fw_cfg file " FW_CFG_FILE " (QEMU -fw_cfg name=" FW_CFG_FILE ",string=...)\n");
		goto out;
	}
	for (i = 0; *p && *p != ' '; p++, i++) {
		if (i == NAME_MAX || *p < 0x21 || *p > 0x7e)
			break;
		name[i] = (uint16_t)*p;
	}
	name[i] = 0;
	if (i == 0 || *p++ != ' ' || hex_bytes(&p, (uint8_t *)&vendor, sizeof(vendor)) != (int64_t)sizeof(vendor)
	    || *p++ != ' ' || (n = hex_bytes(&p, data, sizeof(data))) <= 0 || *p) {
		puts_(MARK "FAIL not \"NAME GUID DATA\" (the GUID 32 hex digits, the data at most 256 bytes): ");
		puts_(text);
		puts_("\n");
		goto out;
	}
	size = (uint64_t)n;

	puts_(MARK "SetVariable ");
	for (i = 0; name[i]; i++)
		putc_((char)name[i]);
	puts_(" ("); putdec(size); puts_(" bytes, NV+BS+RT): ");
	s = st->rt->set_variable(name, &vendor, ATTR_NV | ATTR_BS | ATTR_RT, size, data);
	status_name(s);
	puts_("\n");
	if (EFI_ERR(s))
		goto out;

	back_size = sizeof(back);
	s = st->rt->get_variable(name, &vendor, &attr, &back_size, back);
	puts_(MARK "GetVariable: ");
	status_name(s);
	if (!EFI_ERR(s)) {
		puts_(", attributes 0x"); puthex(attr, 2);
		puts_(", "); putdec(back_size); puts_(" bytes");
		ok = attr == (ATTR_NV | ATTR_BS | ATTR_RT) && back_size == size;
		for (k = 0; ok && k < size; k++)
			ok = back[k] == data[k];
		puts_(ok ? ", as written" : ", not what was written");
	}
	puts_("\n");
out:
	puts_(ok ? MARK "RESULT OK\n" : MARK "RESULT FAIL\n");
	for (;;)
		__asm__ volatile("pause");
}

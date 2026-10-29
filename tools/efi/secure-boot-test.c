/* secure-boot-test.c: Secure Boot image verification and the ESRT of the payload,
 * reported on COM1 (the step 10 of tools/qemu-smoke.py, tools/build.sh smoke).
 *
 * The payload boots this application as \EFI\BOOT\BOOTX64.EFI from an ESP, twice,
 * on the same flash.
 *
 * Boot 1 (the variable store is fresh: EnrollDefaultKeys has put the Microsoft
 * keys in, SecureBootEnable is 0): the ESRT is printed, and SHA-256 and the
 * PBKDF2 of the setup password computed through the crypto protocol of
 * CryptoDxe, for the harness to compare; LoadImage() of every embedded image
 * with Secure Boot off, all accepted; then, in custom mode as
 * EnrollDefaultKeys does, the CA certificate the signature of this application
 * leads to is appended to db and the Authenticode hash of signed-revoked.efi to
 * dbx, SecureBootEnable is set to 1, a marker variable is written and the
 * machine resets.
 *
 * Boot 2 (SecureBoot 1): this application runs only if the payload verified its
 * signature: a leaf certificate in the image, its CA in db, the chain built by
 * the crypto of the payload. The ESRT again, then LoadImage() of each embedded
 * image: the shim signed by Microsoft must pass (the CA of its signature is in
 * db since the first boot), the image signed by a certificate that is in no
 * database, the unsigned image and the image signed by another child of the CA
 * whose Authenticode hash the first boot put in dbx must be refused; the same
 * image with another TimeDateStamp, another hash, signed by that child, must
 * pass. "RESULT OK" closes.
 *
 * The images, the certificate and the hash come in through .incbin from the
 * directory tools/build.sh smoke compiles this in: cert-ca.der, shim-ms.efi
 * (empty when no shim signed by Microsoft is at hand: the case is skipped),
 * signed-other.efi, unsigned.efi, signed-revoked.efi and revoked.hash (its
 * Authenticode SHA-256, tools/pe-hash.py), signed-ok.efi. No library: clang
 * --target=x86_64-unknown-windows, as the other applications of tools/efi;
 * sbsign signs it with the leaf certificate.
 */
#include <stdint.h>
#include <stddef.h>

#define COM1 0x3f8
#define MARK "ouroBIOS sb test: "

typedef uint64_t efi_status;
#define EFI_ERR(s) ((s) >> 63)
#define EFI_SUCCESS 0
#define EFI_NOT_FOUND 0x800000000000000eULL
#define EFI_ACCESS_DENIED 0x800000000000000fULL
#define EFI_SECURITY_VIOLATION 0x800000000000001aULL

struct guid { uint32_t a; uint16_t b, c; uint8_t d[8]; };
struct table_header { uint64_t signature; uint32_t revision, header_size, crc32, reserved; };
struct efi_time { uint16_t year; uint8_t month, day, hour, minute, second, pad1; uint32_t nanosecond;
		  int16_t timezone; uint8_t daylight, pad2; };
struct configuration_table { struct guid vendor_guid; void *vendor_table; };

struct boot_services {
	struct table_header hdr;
	void *raise_tpl, *restore_tpl, *allocate_pages, *free_pages, *get_memory_map, *allocate_pool, *free_pool;
	void *create_event, *set_timer, *wait_for_event, *signal_event, *close_event, *check_event;
	void *install_protocol_interface, *reinstall_protocol_interface, *uninstall_protocol_interface,
	     *handle_protocol, *reserved, *register_protocol_notify, *locate_handle, *locate_device_path,
	     *install_configuration_table;
	efi_status (*load_image)(uint8_t boot_policy, void *parent, void *file_path, void *source,
				 uint64_t source_size, void **image);
	efi_status (*start_image)(void *image, uint64_t *exit_data_size, uint16_t **exit_data);
	void *exit;
	efi_status (*unload_image)(void *image);
	void *exit_boot_services, *get_next_monotonic_count, *stall, *set_watchdog_timer, *connect_controller,
	     *disconnect_controller, *open_protocol, *close_protocol, *open_protocol_information,
	     *protocols_per_handle, *locate_handle_buffer;
	efi_status (*locate_protocol)(struct guid *protocol, void *registration, void **interface);
};
/* The EDK II crypto protocol (CryptoPkg/Private/Protocol/Crypto.h): a table of
 * function pointers, the ones used here at their index */
struct crypto_protocol { void *fn[300]; };
#define CRYPTO_GET_VERSION 0
#define CRYPTO_PKCS5_HASH_PASSWORD 32
#define CRYPTO_SHA256_HASH_ALL 72
typedef uint64_t (*crypto_get_version)(void);
typedef uint8_t (*crypto_pkcs5)(uint64_t password_size, const char *password, uint64_t salt_size,
				const uint8_t *salt, uint64_t iterations, uint64_t digest_size, uint64_t out_size,
				uint8_t *out);
typedef uint8_t (*crypto_sha256_all)(const void *data, uint64_t size, uint8_t *hash);
struct runtime_services {
	struct table_header hdr;
	efi_status (*get_time)(struct efi_time *t, void *caps);
	void *set_time, *get_wakeup_time, *set_wakeup_time, *set_virtual_address_map, *convert_pointer;
	efi_status (*get_variable)(uint16_t *name, struct guid *vendor, uint32_t *attributes,
				   uint64_t *size, void *data);
	void *get_next_variable_name;
	efi_status (*set_variable)(uint16_t *name, struct guid *vendor, uint32_t attributes,
				   uint64_t size, void *data);
	void *get_next_high_mono_count;
	void (*reset_system)(uint32_t type, efi_status status, uint64_t size, void *data);
};
struct system_table {
	struct table_header hdr;
	uint16_t *firmware_vendor;
	uint32_t firmware_revision;
	void *console_in_handle, *con_in, *console_out_handle, *con_out, *standard_error_handle, *std_err;
	struct runtime_services *rt;
	struct boot_services *bs;
	uint64_t number_of_table_entries;
	struct configuration_table *configuration_table;
};
struct esrt_entry {
	struct guid fw_class;
	uint32_t fw_type, fw_version, lowest_supported_fw_version, capsule_flags;
	uint32_t last_attempt_version, last_attempt_status;
};
struct esrt { uint32_t count, max, version_hi, version_lo; struct esrt_entry entries[]; };
_Static_assert(offsetof(struct boot_services, load_image) == 0xc8, "LoadImage");
_Static_assert(offsetof(struct boot_services, unload_image) == 0xe0, "UnloadImage");
_Static_assert(offsetof(struct boot_services, locate_protocol) == 0x140, "LocateProtocol");
_Static_assert(offsetof(struct runtime_services, get_variable) == 0x48, "GetVariable");
_Static_assert(offsetof(struct runtime_services, set_variable) == 0x58, "SetVariable");
_Static_assert(offsetof(struct runtime_services, reset_system) == 0x68, "ResetSystem");

#define ATTR_NV 1u
#define ATTR_BS 2u
#define ATTR_RT 4u
#define ATTR_TIME_AUTH 0x20u
#define ATTR_APPEND 0x40u

static struct guid global_var = { 0x8be4df61, 0x93ca, 0x11d2, { 0xaa, 0x0d, 0x00, 0xe0, 0x98, 0x03, 0x2b, 0x8c } };
static struct guid image_db = { 0xd719b2cb, 0x3d3a, 0x4596, { 0xa3, 0xbc, 0xda, 0xd0, 0x0e, 0x67, 0x65, 0x6f } };
static struct guid sb_enable = { 0xf0a30bc7, 0xaf08, 0x4556, { 0x99, 0xc4, 0x00, 0x10, 0x09, 0xc9, 0x3a, 0x44 } };
static struct guid custom_mode = { 0xc076ec0c, 0x7028, 0x4399, { 0xa0, 0x72, 0x71, 0xee, 0x5c, 0x44, 0x8b, 0x9f } };
static struct guid cert_x509 = { 0xa5c059a1, 0x94e4, 0x4aa7, { 0x87, 0xb5, 0xab, 0x15, 0x5c, 0x2b, 0xf0, 0x72 } };
static struct guid cert_pkcs7 = { 0x4aafd29d, 0x68df, 0x49ee, { 0x8a, 0xa9, 0x34, 0x7d, 0x37, 0x56, 0x65, 0xa7 } };
static struct guid cert_sha256 = { 0xc1c41626, 0x504c, 0x4092, { 0xac, 0xa9, 0x41, 0xf9, 0x36, 0x93, 0x43, 0x28 } };
static struct guid esrt_guid = { 0xb122a263, 0x3661, 0x4f68, { 0x99, 0x29, 0x78, 0xf8, 0xb0, 0xd6, 0x21, 0x80 } };
static struct guid crypto_guid = { 0x2c2275c9, 0x3a7b, 0x426f, { 0xbe, 0x54, 0x2d, 0x22, 0xbd, 0x9d, 0x10, 0x92 } };
/* the marker variable and the owner of the certificate: a GUID of this test */
static struct guid test_guid = { 0x5b2c5e0a, 0x0b5f, 0x4e0e, { 0x9c, 0x41, 0x2d, 0x6f, 0x8a, 0x3b, 0x7e, 0x51 } };

static uint16_t name_setup_mode[] = u"SetupMode";
static uint16_t name_secure_boot[] = u"SecureBoot";
static uint16_t name_sb_enable[] = u"SecureBootEnable";
static uint16_t name_custom[] = u"CustomMode";
static uint16_t name_db[] = u"db";
static uint16_t name_dbx[] = u"dbx";
static uint16_t name_marker[] = u"OuroSbTest";

/* the embedded images and the certificate (the files of the build directory) */
#define BLOB(sym, file) \
	__asm__(".section .rodata\n.balign 16\n.globl " #sym "\n" #sym ":\n.incbin \"" file "\"\n" \
		".globl " #sym "_end\n" #sym "_end:\n.byte 0\n.text\n"); \
	extern const uint8_t sym[], sym##_end[];
BLOB(blob_shim_ms, "shim-ms.efi")
BLOB(blob_signed_other, "signed-other.efi")
BLOB(blob_unsigned, "unsigned.efi")
BLOB(blob_signed_revoked, "signed-revoked.efi")
BLOB(blob_signed_ok, "signed-ok.efi")
BLOB(blob_revoked_hash, "revoked.hash")
BLOB(blob_cert, "cert-ca.der")

static inline void outb(uint16_t port, uint8_t v) { __asm__ volatile("outb %0, %1" : : "a"(v), "Nd"(port)); }
static inline uint8_t inb(uint16_t port) { uint8_t v; __asm__ volatile("inb %1, %0" : "=a"(v) : "Nd"(port)); return v; }
static void putc_(char c) { int i; for (i = 0; i < 100000 && !(inb(COM1 + 5) & 0x20); i++) { } outb(COM1, (uint8_t)c); }
static void puts_(const char *s) { for (; *s; s++) { if (*s == '\n') putc_('\r'); putc_(*s); } }
static void puthex(uint64_t v, int digits) { int s; for (s = (digits - 1) * 4; s >= 0; s -= 4) putc_("0123456789abcdef"[(v >> s) & 0xf]); }
static void putdec(uint64_t v) { char b[21]; int i = 20; b[i] = 0; do { b[--i] = (char)('0' + v % 10); v /= 10; } while (v); puts_(b + i); }
static void putguid(const struct guid *g)
{
	int i;
	puthex(g->a, 8); putc_('-'); puthex(g->b, 4); putc_('-'); puthex(g->c, 4); putc_('-');
	puthex(g->d[0], 2); puthex(g->d[1], 2); putc_('-');
	for (i = 2; i < 8; i++) puthex(g->d[i], 2);
}
static int guid_eq(const struct guid *x, const struct guid *y)
{
	const uint8_t *p = (const uint8_t *)x, *q = (const uint8_t *)y;
	int i;
	for (i = 0; i < 16; i++) if (p[i] != q[i]) return 0;
	return 1;
}
static void status_name(efi_status s)
{
	if (s == EFI_SUCCESS) puts_("SUCCESS");
	else if (s == EFI_ACCESS_DENIED) puts_("ACCESS_DENIED");
	else if (s == EFI_SECURITY_VIOLATION) puts_("SECURITY_VIOLATION");
	else if (s == EFI_NOT_FOUND) puts_("NOT_FOUND");
	else { puts_("0x"); puthex(s, 16); }
}

static struct system_table *st;
static void *self_image;
static int failures;

static void print_esrt(void)
{
	const struct esrt *esrt = NULL;
	uint64_t i;
	for (i = 0; i < st->number_of_table_entries; i++)
		if (guid_eq(&st->configuration_table[i].vendor_guid, &esrt_guid))
			esrt = st->configuration_table[i].vendor_table;
	if (!esrt) {
		puts_(MARK "no ESRT\n");
		return;
	}
	for (i = 0; i < esrt->count; i++) {
		const struct esrt_entry *e = &esrt->entries[i];
		puts_(MARK "esrt "); putguid(&e->fw_class);
		puts_(" type "); putdec(e->fw_type);
		puts_(" version 0x"); puthex(e->fw_version, 8);
		puts_(" lsv 0x"); puthex(e->lowest_supported_fw_version, 8);
		puts_(" last 0x"); puthex(e->last_attempt_version, 8);
		puts_(" status 0x"); puthex(e->last_attempt_status, 8);
		puts_("\n");
	}
	puts_(MARK "esrt entries "); putdec(esrt->count); puts_("\n");
}

static int get_u8(uint16_t *name, struct guid *vendor, uint8_t *out)
{
	uint64_t size = 1;
	uint32_t attr = 0;
	efi_status s = st->rt->get_variable(name, vendor, &attr, &size, out);
	return EFI_ERR(s) ? -1 : (int)attr;
}

static void show_u8(const char *label, uint16_t *name, struct guid *vendor)
{
	uint8_t v = 0xff;
	int attr = get_u8(name, vendor, &v);
	puts_(MARK); puts_(label); puts_(" = ");
	if (attr < 0) puts_("absent"); else { putdec(v); puts_(" attr 0x"); puthex((uint64_t)attr, 2); }
	puts_("\n");
}

/* LoadImage() of an embedded image, never started; expect is "SUCCESS" or the
 * name of an error: a verdict that does not match counts as a failure */
static void try_load(const char *label, const uint8_t *buf, const uint8_t *end, const char *expect)
{
	void *image = NULL;
	efi_status s;
	int ok;
	puts_(MARK "LoadImage "); puts_(label);
	if (end == buf) {
		puts_(": skipped, no image\n");
		return;
	}
	s = st->bs->load_image(0, self_image, (void *)0, (void *)buf, (uint64_t)(end - buf), &image);
	puts_(" ("); putdec((uint64_t)(end - buf)); puts_(" bytes): ");
	status_name(s);
	puts_(", expected "); puts_(expect);
	ok = (s == EFI_SUCCESS) == (expect[0] == 'S');
	puts_(ok ? " -> ok\n" : " -> WRONG\n");
	if (!ok)
		failures++;
	if (image && (s == EFI_SUCCESS || s == EFI_SECURITY_VIOLATION))
		st->bs->unload_image(image);
}

static void set_u8(const char *label, uint16_t *name, struct guid *vendor, uint32_t attr, uint8_t v)
{
	efi_status s = st->rt->set_variable(name, vendor, attr, 1, &v);
	puts_(MARK "SetVariable "); puts_(label); puts_(" = "); putdec(v); puts_(": "); status_name(s); puts_("\n");
	if (EFI_ERR(s))
		failures++;
}

/* name (db or dbx) <- one signature of the given type (an X.509 certificate, a
 * SHA-256), appended in custom mode: an EFI_VARIABLE_AUTHENTICATION_2 without a
 * signature and an EFI_SIGNATURE_LIST with one entry, as EnrollDefaultKeys
 * writes the Microsoft keys */
static efi_status enroll(uint16_t *name, const struct guid *type, const uint8_t *blob, uint64_t cert_size)
{
	static uint8_t data[8192];
	uint8_t *p = data;
	struct efi_time t;
	uint64_t i;

	if (40 + 28 + 16 + cert_size > sizeof data)
		return EFI_ACCESS_DENIED;
	for (i = 0; i < sizeof data; i++) data[i] = 0;
	for (i = 0; i < sizeof t; i++) ((uint8_t *)&t)[i] = 0;
	if (EFI_ERR(st->rt->get_time(&t, (void *)0))) {
		t.year = 2018; t.month = 1; t.day = 1;
	}
	t.pad1 = 0; t.nanosecond = 0; t.timezone = 0; t.daylight = 0; t.pad2 = 0;
	for (i = 0; i < sizeof t; i++) p[i] = ((uint8_t *)&t)[i];
	p += 16;
	*(uint32_t *)p = 24;		/* dwLength: WIN_CERTIFICATE and CertType, no CertData */
	*(uint16_t *)(p + 4) = 0x0200;	/* wRevision */
	*(uint16_t *)(p + 6) = 0x0ef1;	/* WIN_CERT_TYPE_EFI_GUID */
	for (i = 0; i < 16; i++) p[8 + i] = ((uint8_t *)&cert_pkcs7)[i];
	p += 24;
	/* EFI_SIGNATURE_LIST */
	for (i = 0; i < 16; i++) p[i] = ((const uint8_t *)type)[i];
	*(uint32_t *)(p + 16) = (uint32_t)(28 + 16 + cert_size);	/* SignatureListSize */
	*(uint32_t *)(p + 20) = 0;					/* SignatureHeaderSize */
	*(uint32_t *)(p + 24) = (uint32_t)(16 + cert_size);		/* SignatureSize */
	p += 28;
	for (i = 0; i < 16; i++) p[i] = ((uint8_t *)&test_guid)[i];	/* SignatureOwner */
	p += 16;
	for (i = 0; i < cert_size; i++) p[i] = blob[i];
	p += cert_size;
	return st->rt->set_variable(name, &image_db,
				    ATTR_NV | ATTR_BS | ATTR_RT | ATTR_TIME_AUTH | ATTR_APPEND,
				    (uint64_t)(p - data), data);
}

/* The crypto protocol of CryptoDxe, as UserAuthenticationDxe hashes the setup
 * password (PBKDF2-HMAC-SHA256, 1000 iterations, a 32 byte salt, 32 bytes out)
 * and as everything hashes: the values on the serial line, for the harness */
static void crypto_protocol_test(void)
{
	static const char password[] = "ouroBIOS";
	uint8_t salt[32], out[32];
	struct crypto_protocol *cp = (void *)0;
	efi_status s;
	int i;
	for (i = 0; i < 32; i++) salt[i] = (uint8_t)i;
	s = st->bs->locate_protocol(&crypto_guid, (void *)0, (void **)&cp);
	if (EFI_ERR(s) || !cp) {
		puts_(MARK "crypto protocol: absent\n");
		return;
	}
	puts_(MARK "crypto protocol: version "); putdec(((crypto_get_version)cp->fn[CRYPTO_GET_VERSION])());
	puts_("\n" MARK "sha256 abc = ");
	if (((crypto_sha256_all)cp->fn[CRYPTO_SHA256_HASH_ALL])("abc", 3, out)) {
		for (i = 0; i < 32; i++) puthex(out[i], 2);
	} else {
		puts_("FALSE");
	}
	puts_("\n" MARK "pbkdf2 sha256 ouroBIOS salt 0..31 1000 = ");
	if (((crypto_pkcs5)cp->fn[CRYPTO_PKCS5_HASH_PASSWORD])(sizeof password - 1, password, sizeof salt, salt,
							       1000, 32, sizeof out, out)) {
		for (i = 0; i < 32; i++) puthex(out[i], 2);
	} else {
		puts_("FALSE");
	}
	puts_("\n");
}

__attribute__((ms_abi)) efi_status efi_main(void *image, struct system_table *table)
{
	uint8_t marker = 0, secure_boot = 0;
	efi_status s;
	self_image = image;
	st = table;

	puts_("\n" MARK "firmware revision 0x"); puthex(st->firmware_revision, 8); puts_("\n");
	print_esrt();
	show_u8("SetupMode", name_setup_mode, &global_var);
	show_u8("SecureBoot", name_secure_boot, &global_var);
	show_u8("SecureBootEnable", name_sb_enable, &sb_enable);
	show_u8("CustomMode", name_custom, &custom_mode);
	if (get_u8(name_marker, &test_guid, &marker) < 0) {
		crypto_protocol_test();
		puts_(MARK "boot 1: Secure Boot off, every image loads\n");
		try_load("shim-ms", blob_shim_ms, blob_shim_ms_end, "SUCCESS");
		try_load("signed-other", blob_signed_other, blob_signed_other_end, "SUCCESS");
		try_load("unsigned", blob_unsigned, blob_unsigned_end, "SUCCESS");
		try_load("signed-revoked", blob_signed_revoked, blob_signed_revoked_end, "SUCCESS");
		try_load("signed-ok", blob_signed_ok, blob_signed_ok_end, "SUCCESS");
		puts_(MARK "boot 1: the test CA into db and the hash of signed-revoked into dbx, in custom "
		      "mode; Secure Boot on\n");
		set_u8("CustomMode", name_custom, &custom_mode, ATTR_NV | ATTR_BS, 1);
		s = enroll(name_db, &cert_x509, blob_cert, (uint64_t)(blob_cert_end - blob_cert));
		puts_(MARK "SetVariable db append, "); putdec((uint64_t)(blob_cert_end - blob_cert));
		puts_(" byte certificate: "); status_name(s); puts_("\n");
		if (EFI_ERR(s))
			failures++;
		s = enroll(name_dbx, &cert_sha256, blob_revoked_hash,
			   (uint64_t)(blob_revoked_hash_end - blob_revoked_hash));
		puts_(MARK "SetVariable dbx append, "); putdec((uint64_t)(blob_revoked_hash_end - blob_revoked_hash));
		puts_(" byte hash: "); status_name(s); puts_("\n");
		if (EFI_ERR(s))
			failures++;
		set_u8("CustomMode", name_custom, &custom_mode, ATTR_NV | ATTR_BS, 0);
		set_u8("SecureBootEnable", name_sb_enable, &sb_enable, ATTR_NV | ATTR_BS, 1);
		set_u8("OuroSbTest", name_marker, &test_guid, ATTR_NV | ATTR_BS, 1);
		if (failures) {
			puts_(MARK "RESULT FAIL: boot 1\n");
			for (;;) { }
		}
		puts_(MARK "reset\n");
		st->rt->reset_system(0 /* cold */, 0, 0, (void *)0);
		puts_(MARK "RESULT FAIL: ResetSystem() returned\n");
		for (;;) { }
	}
	get_u8(name_secure_boot, &global_var, &secure_boot);
	puts_(MARK "boot 2: this application loaded with SecureBoot = "); putdec(secure_boot); puts_("\n");
	if (secure_boot != 1)
		failures++;
	try_load("shim-ms", blob_shim_ms, blob_shim_ms_end, "SUCCESS");
	try_load("signed-other", blob_signed_other, blob_signed_other_end, "ACCESS_DENIED");
	try_load("unsigned", blob_unsigned, blob_unsigned_end, "ACCESS_DENIED");
	try_load("signed-revoked", blob_signed_revoked, blob_signed_revoked_end, "ACCESS_DENIED");
	try_load("signed-ok", blob_signed_ok, blob_signed_ok_end, "SUCCESS");
	puts_(failures ? MARK "RESULT FAIL\n" : MARK "RESULT OK\n");
	for (;;) { }
	return EFI_SUCCESS;
}

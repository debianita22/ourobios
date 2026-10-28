/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * rt-reloc-test.c - per la prova di fumo (tools/qemu-smoke.py, passo 9):
 * un'applicazione UEFI, \EFI\BOOT\BOOTX64.EFI dell'ESP, che fa con i servizi
 * runtime quello che fa boot.efi di macOS senza AvoidRuntimeDefrag di
 * OpenCore. Dopo ExitBootServices() e SetVirtualAddressMap() copia il codice
 * e i dati dei servizi runtime (EfiRuntimeServicesCode e Data) in altra
 * memoria, riempie di 0xCC le copie di prima e chiama i servizi con tabelle
 * delle pagine che hanno solo le aree con EFI_MEMORY_RUNTIME, agli indirizzi
 * virtuali (le copie nuove; l'MMIO resta dov'e', come lo lascia boot.efi), e
 * l'applicazione. Un indirizzo fisico che il payload usa ancora a runtime
 * manda la CPU in triple fault (l'IDT non e' mappata) e QEMU esce; uno che
 * usa SMM, che non passa da queste tabelle, legge 0xCC: la variabile non si
 * scrive, o si scrive sbagliata. Fino a v1.3.10-rc15 gli argomenti di
 * SMMSTORE (in rc15 anche il com buffer) erano dati dei servizi runtime, e
 * SetVariable() falliva cosi' (EFI_DEVICE_ERROR); da rc16 sono MMIO (patch
 * 0134, edk2/0029).
 * Scrive e rilegge due variabili di prova, chiama gli altri servizi che si
 * possono chiamare senza effetti fuori dalla prova, conta i byte scritti
 * nelle copie di prima, scrive l'esito sulla seriale (COM1) e chiama
 * ResetSystem(); la prova legge seriale e flash.
 *
 * Nessuna libreria: tools/build.sh la compila come slot-lock-test.c, con
 *   clang --target=x86_64-unknown-windows -ffreestanding -nostdlib -fuse-ld=lld
 *         -Wl,-subsystem:efi_application -Wl,-entry:efi_main
 * e le chiamate ai servizi UEFI usano l'ABI di Microsoft, quella di quel target.
 */

#include <stddef.h>
#include <stdint.h>

#define COM1			0x3f8
#define RST_CNT			0xcf9		/* reset dell'ICH9 di q35 */
#define FULL_RESET		0x0e

#define EFI_LOADER_CODE		1
#define EFI_LOADER_DATA		2
#define EFI_RUNTIME_CODE	5
#define EFI_RUNTIME_DATA	6
#define EFI_CONVENTIONAL_MEMORY	7
#define EFI_MEMORY_RUNTIME	(1ULL << 63)
#define EFI_NOT_FOUND		0x800000000000000eULL
#define VAR_NV_BS_RT		7
#define EFI_RESET_COLD		0

/* Gli indirizzi virtuali dei servizi runtime: VIRT + l'indirizzo fisico */
#define VIRT			0xffff800000000000ULL
#define MAX_MOVED		64
#define PAGE			4096ULL

typedef uint64_t efi_status;

/* EFI_MEMORY_DESCRIPTOR (UEFI 2.10, 7.2); nella mappa a passi di descriptor_size */
struct memory_descriptor {
	uint32_t type, pad;
	uint64_t physical_start, virtual_start, number_of_pages, attribute;
};

struct table_header {
	uint64_t signature;
	uint32_t revision, header_size, crc32, reserved;
};

struct guid {
	uint32_t data1;
	uint16_t data2, data3;
	uint8_t data4[8];
};

/* EFI_TIME */
struct time {
	uint16_t year;
	uint8_t month, day, hour, minute, second, pad1;
	uint32_t nanosecond;
	int16_t time_zone;
	uint8_t daylight, pad2;
};

/* EFI_CAPSULE_HEADER */
struct capsule_header {
	struct guid capsule_guid;
	uint32_t header_size, flags, capsule_image_size;
};

/* EFI_BOOT_SERVICES fino a ExitBootServices() (UEFI 2.10, 4.4) */
struct boot_services {
	struct table_header hdr;
	void *raise_tpl, *restore_tpl, *allocate_pages, *free_pages;
	efi_status (*get_memory_map)(uint64_t *size, void *map, uint64_t *key,
				     uint64_t *descriptor_size, uint32_t *descriptor_version);
	void *allocate_pool, *free_pool, *create_event, *set_timer, *wait_for_event,
	     *signal_event, *close_event, *check_event, *install_protocol_interface,
	     *reinstall_protocol_interface, *uninstall_protocol_interface,
	     *handle_protocol, *reserved, *register_protocol_notify, *locate_handle,
	     *locate_device_path, *install_configuration_table, *load_image,
	     *start_image, *exit, *unload_image;
	efi_status (*exit_boot_services)(void *image, uint64_t key);
};

/* EFI_RUNTIME_SERVICES (UEFI 2.10, 4.5) */
struct runtime_services {
	struct table_header hdr;
	efi_status (*get_time)(struct time *time, void *capabilities);
	efi_status (*set_time)(struct time *time);
	efi_status (*get_wakeup_time)(uint8_t *enabled, uint8_t *pending, struct time *time);
	efi_status (*set_wakeup_time)(uint8_t enable, struct time *time);
	efi_status (*set_virtual_address_map)(uint64_t size, uint64_t descriptor_size,
					      uint32_t version, void *map);
	void *convert_pointer;
	efi_status (*get_variable)(uint16_t *name, struct guid *vendor, uint32_t *attributes,
				   uint64_t *size, void *data);
	efi_status (*get_next_variable_name)(uint64_t *size, uint16_t *name, struct guid *vendor);
	efi_status (*set_variable)(uint16_t *name, struct guid *vendor, uint32_t attributes,
				   uint64_t size, void *data);
	efi_status (*get_next_high_monotonic_count)(uint32_t *high);
	void (*reset_system)(uint32_t type, efi_status status, uint64_t size, void *data);
	void *update_capsule;
	efi_status (*query_capsule_capabilities)(struct capsule_header **capsules, uint64_t count,
						 uint64_t *max_size, uint32_t *reset_type);
	efi_status (*query_variable_info)(uint32_t attributes, uint64_t *max_storage,
					  uint64_t *remaining, uint64_t *max_variable);
};

/* EFI_SYSTEM_TABLE (UEFI 2.10, 4.3) */
struct system_table {
	struct table_header hdr;
	void *firmware_vendor;
	uint32_t firmware_revision;
	void *console_in_handle, *con_in, *console_out_handle, *con_out,
	     *standard_error_handle, *std_err;
	struct runtime_services *runtime_services;
	struct boot_services *boot_services;
};

_Static_assert(offsetof(struct boot_services, get_memory_map) == 0x38, "GetMemoryMap");
_Static_assert(offsetof(struct boot_services, exit_boot_services) == 0xe8, "ExitBootServices");
_Static_assert(offsetof(struct runtime_services, set_virtual_address_map) == 0x38, "SVAM");
_Static_assert(offsetof(struct runtime_services, get_variable) == 0x48, "GetVariable");
_Static_assert(offsetof(struct runtime_services, reset_system) == 0x68, "ResetSystem");
_Static_assert(offsetof(struct runtime_services, query_capsule_capabilities) == 0x78, "QCC");
_Static_assert(offsetof(struct runtime_services, query_variable_info) == 0x80, "QVI");
_Static_assert(offsetof(struct system_table, runtime_services) == 0x58, "RuntimeServices");
_Static_assert(sizeof(struct time) == 16, "EFI_TIME");
_Static_assert(sizeof(struct capsule_header) == 28, "EFI_CAPSULE_HEADER");

/* Le variabili di prova: tools/qemu-smoke.py le cerca nel flash, con questi dati */
static struct guid vendor = {
	0x98fd63b7, 0xd585, 0x401b, { 0x9a, 0xd3, 0x7b, 0xf5, 0xbe, 0x11, 0x5a, 0x84 }
};
static uint16_t name_a[] = u"OuroRelocA";	/* 16 byte, 0x40 + i */
static uint16_t name_b[] = u"OuroRelocB";	/* 3000 byte, (7 * i + 3) & 0xff */
static uint8_t data_a[16], data_b[3000], readback[4096];

/* Solo l'intestazione di una capsula FMP: QueryCapsuleCapabilities() la accetta */
static struct capsule_header fmp_capsule = {
	{ 0x6dcbd5ed, 0xe82d, 0x4c44, { 0xbd, 0xa1, 0x71, 0x94, 0x19, 0x9a, 0xd9, 0x2a } },
	sizeof(struct capsule_header), 0, sizeof(struct capsule_header)
};

/* Le copie di prima, per contare alla fine i byte che non sono piu' 0xCC */
static struct {
	uint64_t start, pages;
} moved[MAX_MOVED];
static unsigned int moved_count;

static uint8_t memory_map[64 * 1024] __attribute__((aligned(8)));
static uint8_t virtual_map[64 * 1024] __attribute__((aligned(8)));
static uint8_t page_pool[1024 * PAGE] __attribute__((aligned(4096)));
static uint8_t stack[64 * 1024] __attribute__((aligned(16)));
static uint64_t pool_used, firmware_cr3, test_cr3;
static struct runtime_services *rt;	/* l'indirizzo virtuale */
static int failures;

static inline void outb(uint16_t port, uint8_t value)
{
	__asm__ volatile("outb %0, %1" : : "a"(value), "Nd"(port));
}

static inline uint8_t inb(uint16_t port)
{
	uint8_t value;

	__asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(port));
	return value;
}

/* rep movsb e rep stosb: il compilatore non li trasforma in chiamate */
static void copy(void *dst, const void *src, uint64_t n)
{
	__asm__ volatile("rep movsb" : "+D"(dst), "+S"(src), "+c"(n) : : "memory");
}

static void fill(void *dst, uint8_t value, uint64_t n)
{
	__asm__ volatile("rep stosb" : "+D"(dst), "+c"(n) : "a"(value) : "memory");
}

/* Se il compilatore le chiama per inizializzare una variabile locale */
void *memset(void *dst, int value, size_t n)
{
	fill(dst, (uint8_t)value, n);
	return dst;
}

void *memcpy(void *dst, const void *src, size_t n)
{
	copy(dst, src, n);
	return dst;
}

static void set_cr3(uint64_t cr3)
{
	__asm__ volatile("mov %0, %%cr3" : : "r"(cr3) : "memory");
}

/* La UART resta come l'ha programmata il firmware */
static void serial_putc(char c)
{
	int i;

	for (i = 0; i < 100000 && !(inb(COM1 + 5) & 0x20); i++)
		;
	outb(COM1, (uint8_t)c);
}

static void serial_puts(const char *s)
{
	for (; *s; s++) {
		if (*s == '\n')
			serial_putc('\r');
		serial_putc(*s);
	}
}

static void serial_putu(uint64_t value)
{
	char digits[21];
	int i = sizeof(digits) - 1;

	digits[i] = '\0';
	do {
		digits[--i] = (char)('0' + value % 10);
		value /= 10;
	} while (value);
	serial_puts(&digits[i]);
}

static void serial_puthex(uint64_t value)
{
	int shift;

	serial_puts("0x");
	for (shift = 60; shift >= 0; shift -= 4)
		serial_putc("0123456789abcdef"[(value >> shift) & 0xf]);
}

static void say(const char *what)
{
	serial_puts("ouroBIOS reloc test: ");
	serial_puts(what);
}

static __attribute__((noreturn)) void reset(void)
{
	outb(RST_CNT, FULL_RESET);
	for (;;)
		__asm__ volatile("cli; hlt");
}

static __attribute__((noreturn)) void fail(const char *what)
{
	say("FAIL ");
	serial_puts(what);
	serial_puts("\n");
	say("RESULT FAIL\n");
	reset();
}

/* Un servizio che deve riuscire; label dopo il nome, per le variabili */
static void check_label(const char *what, const char *label, efi_status status)
{
	say(what);
	serial_puts(label);
	if (status) {
		serial_puts(": FAIL ");
		serial_puthex(status);
		failures++;
	} else {
		serial_puts(": ok");
	}
	serial_puts("\n");
}

static void check(const char *what, efi_status status)
{
	check_label(what, "", status);
}

/* Un servizio che puo' anche non esserci: solo la risposta */
static void info(const char *what, efi_status status)
{
	say(what);
	serial_puts(": ");
	serial_puthex(status);
	serial_puts("\n");
}

static int same(const volatile uint8_t *a, const volatile uint8_t *b, uint64_t n)
{
	while (n--)
		if (*a++ != *b++)
			return 0;
	return 1;
}

/* Una tabella delle pagine dal pool, a zero */
static uint64_t *new_table(void)
{
	uint64_t *t;

	if (pool_used + PAGE > sizeof(page_pool))
		fail("page tables: pool exhausted");
	t = (uint64_t *)(page_pool + pool_used);
	pool_used += PAGE;
	fill(t, 0, PAGE);
	return t;
}

/* Pagine di 4 KiB a quattro livelli: presenti, scrivibili, senza il bit G */
static void map(uint64_t *pml4, uint64_t va, uint64_t pa, uint64_t pages)
{
	for (; pages; pages--, va += PAGE, pa += PAGE) {
		uint64_t *t = pml4;
		int shift;

		for (shift = 39; shift > 12; shift -= 9) {
			uint64_t *e = &t[(va >> shift) & 511];

			if (!(*e & 1))
				*e = (uint64_t)(uintptr_t)new_table() | 3;
			t = (uint64_t *)(uintptr_t)(*e & 0x000ffffffffff000ULL);
		}
		t[(va >> 12) & 511] = (pa & 0x000ffffffffff000ULL) | 3;
	}
}

/* Scritta, poi riletta (dalla copia in RAM del driver delle variabili) */
static void variable(uint16_t *name, const char *label, uint8_t *data, uint64_t n)
{
	uint64_t size = sizeof(readback);
	uint32_t attributes = 0;
	efi_status status;

	check_label("SetVariable ", label, rt->set_variable(name, &vendor, VAR_NV_BS_RT, n, data));
	status = rt->get_variable(name, &vendor, &attributes, &size, readback);
	if (!status && (size != n || attributes != VAR_NV_BS_RT || !same(readback, data, n))) {
		say("GetVariable ");
		serial_puts(label);
		serial_puts(": FAIL data\n");
		failures++;
		return;
	}
	check_label("GetVariable ", label, status);
}

/* Con le tabelle del firmware, che hanno tutta la memoria 1:1 */
static void scan_old_copies(void)
{
	uint64_t changed = 0, first = 0, i;
	unsigned int r;

	set_cr3(firmware_cr3);
	for (r = 0; r < moved_count; r++) {
		const volatile uint8_t *p = (const volatile uint8_t *)(uintptr_t)moved[r].start;

		for (i = 0; i < moved[r].pages * PAGE; i++) {
			if (p[i] == 0xcc)
				continue;
			if (!changed)
				first = moved[r].start + i;
			changed++;
		}
	}
	set_cr3(test_cr3);
	say("bytes written to the old copies: ");
	if (changed)
		serial_puts("FAIL ");
	serial_putu(changed);
	if (changed) {
		serial_puts(", the first at ");
		serial_puthex(first);
		failures++;
	}
	serial_puts("\n");
}

/* Sulla pila e con le tabelle delle pagine della prova */
static __attribute__((noreturn)) void services(void)
{
	struct capsule_header *capsules[1] = { &fmp_capsule };
	uint64_t size, storage = 0, remaining = 0, largest = 0, capsule_size = 0;
	uint32_t high = 0, reset_type = 0;
	uint8_t enabled = 0, pending = 0;
	uint16_t name[512];
	struct time now, wakeup;
	struct guid guid;
	efi_status status;
	unsigned int n;

	say("calling the runtime services\n");
	status = rt->get_time(&now, 0);
	check("GetTime", status);
	if (!status)
		check("SetTime", rt->set_time(&now));	/* la stessa ora */
	info("GetWakeupTime", rt->get_wakeup_time(&enabled, &pending, &wakeup));
	info("SetWakeupTime off", rt->set_wakeup_time(0, 0));

	variable(name_a, "OuroRelocA", data_a, sizeof(data_a));
	variable(name_b, "OuroRelocB", data_b, sizeof(data_b));

	name[0] = 0;
	status = 0;
	for (n = 0; n < 4096 && !status; n++) {
		size = sizeof(name);
		status = rt->get_next_variable_name(&size, name, &guid);
	}
	say("GetNextVariableName: ");
	serial_putu(n - 1);
	serial_puts(" names\n");
	if (status != EFI_NOT_FOUND)
		check("GetNextVariableName, the end", status);
	check("QueryVariableInfo", rt->query_variable_info(VAR_NV_BS_RT, &storage, &remaining,
							   &largest));
	check("GetNextHighMonotonicCount", rt->get_next_high_monotonic_count(&high));
	info("QueryCapsuleCapabilities", rt->query_capsule_capabilities(capsules, 1, &capsule_size,
									&reset_type));
	scan_old_copies();

	if (failures) {
		say("RESULT FAIL\n");
		reset();
	}
	say("RESULT OK\n");
	say("ResetSystem()\n");
	rt->reset_system(EFI_RESET_COLD, 0, 0, 0);
	say("ResetSystem() returned\n");
	reset();
}

efi_status efi_main(void *image, struct system_table *st)
{
	struct boot_services *bs = st->boot_services;
	uint64_t size, key, descriptor_size, offset, vsize = 0, pages = 0, next = 0, in_place = 0;
	uint64_t cr0, cr4, top, *pml4;
	uint32_t version;
	efi_status status;
	unsigned int i;

	for (i = 0; i < sizeof(data_a); i++)
		data_a[i] = (uint8_t)(0x40 + i);
	for (i = 0; i < sizeof(data_b); i++)
		data_b[i] = (uint8_t)(7 * i + 3);

	say("ExitBootServices()\n");
	for (i = 0; i < 8; i++) {
		size = sizeof(memory_map);
		if (bs->get_memory_map(&size, memory_map, &key, &descriptor_size, &version))
			continue;
		if (!bs->exit_boot_services(image, key))
			break;
	}
	if (i == 8)
		fail("ExitBootServices()");
	__asm__ volatile("cli");

	/* La mappa virtuale: ogni area con EFI_MEMORY_RUNTIME a VIRT + fisico */
	for (offset = 0; offset + descriptor_size <= size; offset += descriptor_size) {
		struct memory_descriptor *d = (void *)(memory_map + offset);

		if (!(d->attribute & EFI_MEMORY_RUNTIME))
			continue;
		d->virtual_start = d->physical_start + VIRT;
		copy(virtual_map + vsize, d, descriptor_size);
		vsize += descriptor_size;
		if (d->type == EFI_RUNTIME_CODE || d->type == EFI_RUNTIME_DATA)
			pages += d->number_of_pages;
	}
	/* Le copie nuove in memoria libera, sopra 1 MiB */
	for (offset = 0; offset + descriptor_size <= size; offset += descriptor_size) {
		struct memory_descriptor *d = (void *)(memory_map + offset);

		if (d->type == EFI_CONVENTIONAL_MEMORY && d->physical_start >= 0x100000 &&
		    d->number_of_pages >= pages) {
			next = d->physical_start;
			break;
		}
	}
	if (!pages || !next)
		fail("no runtime code and data, or no free memory for the copies");

	status = st->runtime_services->set_virtual_address_map(vsize, descriptor_size, version,
								virtual_map);
	say("SetVirtualAddressMap(): ");
	serial_puthex(status);
	serial_puts("\n");
	if (status)
		fail("SetVirtualAddressMap()");
	rt = st->runtime_services;	/* convertito da SetVirtualAddressMap() */

	/* Il codice e i dati dei servizi runtime copiati e le copie di prima a
	   0xCC (CR0.WP spento: il firmware puo' avere lasciato pagine in sola
	   lettura), le pagine virtuali sulle copie nuove; le altre aree runtime
	   (MMIO) al loro posto; l'applicazione 1:1 */
	__asm__ volatile("mov %%cr0, %0" : "=r"(cr0));
	__asm__ volatile("mov %0, %%cr0" : : "r"(cr0 & ~(1ULL << 16)) : "memory");
	pml4 = new_table();
	for (offset = 0; offset < vsize; offset += descriptor_size) {
		struct memory_descriptor *d = (void *)(virtual_map + offset);
		uint64_t bytes = d->number_of_pages * PAGE;

		if (d->type != EFI_RUNTIME_CODE && d->type != EFI_RUNTIME_DATA) {
			map(pml4, d->virtual_start, d->physical_start, d->number_of_pages);
			in_place++;
			continue;
		}
		if (moved_count == MAX_MOVED)
			fail("too many runtime ranges");
		copy((void *)(uintptr_t)next, (void *)(uintptr_t)d->physical_start, bytes);
		fill((void *)(uintptr_t)d->physical_start, 0xcc, bytes);
		map(pml4, d->virtual_start, next, d->number_of_pages);
		moved[moved_count].start = d->physical_start;
		moved[moved_count].pages = d->number_of_pages;
		moved_count++;
		next += bytes;
	}
	for (offset = 0; offset + descriptor_size <= size; offset += descriptor_size) {
		struct memory_descriptor *d = (void *)(memory_map + offset);

		if (d->type == EFI_LOADER_CODE || d->type == EFI_LOADER_DATA)
			map(pml4, d->physical_start, d->physical_start, d->number_of_pages);
	}
	say("moved ");
	serial_putu(moved_count);
	serial_puts(" ranges of runtime code and data (");
	serial_putu(pages);
	serial_puts(" pages), ");
	serial_putu(in_place);
	serial_puts(" other runtime ranges in place\n");

	/* Senza pagine globali nel TLB, poi tabelle e pila della prova */
	__asm__ volatile("mov %%cr4, %0" : "=r"(cr4));
	__asm__ volatile("mov %0, %%cr4" : : "r"(cr4 & ~(1ULL << 7)) : "memory");
	__asm__ volatile("mov %%cr3, %0" : "=r"(firmware_cr3));
	test_cr3 = (uint64_t)(uintptr_t)pml4;
	top = (uint64_t)(uintptr_t)(stack + sizeof(stack)) & ~0xfULL;
	__asm__ volatile("mov %0, %%cr3\n\t"
			 "mov %1, %%rsp\n\t"
			 "sub $32, %%rsp\n\t"
			 "call *%2"
			 : : "r"(test_cr3), "r"(top), "r"(services) : "memory");
	reset();
}

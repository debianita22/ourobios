/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * slot-lock-test.c - per la prova dell'aggiornamento (tools/qemu-update.py):
 * un'applicazione UEFI, \EFI\BOOT\BOOTX64.EFI dell'ESP, che come un boot
 * loader e poi come un sistema operativo chiede a coreboot di avviare
 * l'altro slot di vboot (SMMSTORE_CMD_VBOOT_TRY_OTHER, patch 0065): prima di
 * ExitBootServices(), poi dopo. Il payload lo blocca prima di avviare una
 * voce di boot e a ExitBootServices() (patch edk2/0020): coreboot deve
 * rifiutarlo le due volte, e l'altro slot non deve cambiare. Della mappa
 * della memoria di ExitBootServices(), quella che vede il sistema
 * operativo, conta le aree riservate con EFI_MEMORY_RUNTIME (nessuna) e la
 * memoria libera da 1 MiB a 1 GiB (tutta: il payload e la sua memoria HOB
 * stanno sopra, edk2/0030, e ogni slide del kernel di macOS ci entra), e
 * guarda il com buffer di SMMSTORE, dall'HOB del payload: MMIO con
 * EFI_MEMORY_RUNTIME, con la pagina degli argomenti dopo il blocco (patch
 * 0134, edk2/0029), che boot.efi di macOS non sposta.
 * Scrive le risposte sulla seriale (COM1) e si ferma; la prova legge seriale
 * e flash.
 *
 * Nessuna libreria: tools/build.sh la compila con
 *   clang --target=x86_64-unknown-windows -ffreestanding -nostdlib -fuse-ld=lld
 *         -Wl,-subsystem:efi_application -Wl,-entry:efi_main
 * e le chiamate ai servizi UEFI usano l'ABI di Microsoft, quella di quel target.
 */

#include <stdint.h>

#define COM1				0x3f8
#define APM_CNT				0xb2
#define APM_CNT_SMMSTORE		0xed
#define SMMSTORE_CMD_VBOOT_TRY_OTHER	9

#define EFI_RESERVED_MEMORY_TYPE	0
#define EFI_CONVENTIONAL_MEMORY		7
#define EFI_MEMORY_MAPPED_IO		11
#define EFI_MEMORY_RUNTIME		(1ULL << 63)
#define LOW_START			0x100000ULL	/* 1 MiB */
#define LOW_END				0x40000000ULL	/* 1 GiB, dove comincia il payload */

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

struct guid {
	uint32_t data1;
	uint16_t data2, data3;
	uint8_t data4[8];
};

struct configuration_table {
	struct guid vendor_guid;
	void *vendor_table;
};

/* EFI_SYSTEM_TABLE (UEFI 2.10, 4.3) */
struct system_table {
	struct table_header hdr;
	void *firmware_vendor;
	uint32_t firmware_revision;
	void *console_in_handle, *con_in, *console_out_handle, *con_out,
	     *standard_error_handle, *std_err, *runtime_services;
	struct boot_services *boot_services;
	uint64_t number_of_table_entries;
	struct configuration_table *configuration_table;
};

/* Un HOB (PI 1.8, volume 3): l'intestazione, poi per un HOB GUID il nome */
struct hob_header {
	uint16_t type, length;
	uint32_t reserved;
};

#define HOB_TYPE_GUID_EXTENSION		0x0004
#define HOB_TYPE_END_OF_HOB_LIST	0xffff

/* SMMSTORE_INFO di UefiPayloadPkg (Guid/SmmStoreInfoGuid.h), l'inizio */
struct smmstore_info {
	uint64_t com_buffer;
	uint32_t com_buffer_size, num_blocks, block_size;
};

static const struct guid hob_list_guid = {
	0x7739f24c, 0x93d7, 0x11d4, { 0x9a, 0x3a, 0x00, 0x90, 0x27, 0x3f, 0xc1, 0x4d }
};
static const struct guid smmstore_info_guid = {
	0xf585ca19, 0x881b, 0x44fb, { 0x3f, 0x3d, 0x81, 0x89, 0x7c, 0x57, 0xbb, 0x01 }
};

_Static_assert(__builtin_offsetof(struct boot_services, get_memory_map) == 0x38, "GetMemoryMap");
_Static_assert(__builtin_offsetof(struct boot_services, exit_boot_services) == 0xe8, "ExitBootServices");
_Static_assert(__builtin_offsetof(struct system_table, boot_services) == 0x60, "BootServices");
_Static_assert(__builtin_offsetof(struct system_table, configuration_table) == 0x70,
	       "ConfigurationTable");
_Static_assert(__builtin_offsetof(struct smmstore_info, block_size) == 0x10, "BlockSize");

static uint8_t memory_map[64 * 1024] __attribute__((aligned(8)));
static uint8_t smm_param[64];		/* un parametro qualsiasi, fuori dalla SMRAM */

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

static void serial_putu(uint32_t value)
{
	char digits[11];
	int i = sizeof(digits) - 1;

	digits[i] = '\0';
	do {
		digits[--i] = (char)('0' + value % 10);
		value /= 10;
	} while (value);
	serial_puts(&digits[i]);
}

/* Come SmmStoreLib: comando in AH, APM_CNT_SMMSTORE in AL, parametro in EBX;
   l'SMI handler mette la risposta in EAX */
static uint32_t smmstore(uint8_t command, void *param)
{
	uint32_t eax = ((uint32_t)command << 8) | APM_CNT_SMMSTORE;

	__asm__ volatile("outb %%al, %1"
			 : "+a"(eax)
			 : "N"(APM_CNT), "b"((uint32_t)(uintptr_t)param)
			 : "memory");
	return eax;
}

static int same_guid(const struct guid *a, const struct guid *b)
{
	const uint8_t *x = (const void *)a, *y = (const void *)b;
	unsigned int i;

	for (i = 0; i < sizeof(*a); i++)
		if (x[i] != y[i])
			return 0;
	return 1;
}

/* L'HOB di SMMSTORE del payload, dalla lista degli HOB nella tabella di
   sistema; 0 se non c'e' */
static const struct smmstore_info *find_smmstore(const struct system_table *st)
{
	const uint8_t *hob = 0;
	uint64_t i;

	for (i = 0; i < st->number_of_table_entries; i++)
		if (same_guid(&st->configuration_table[i].vendor_guid, &hob_list_guid))
			hob = st->configuration_table[i].vendor_table;
	while (hob) {
		const struct hob_header *h = (const void *)hob;

		if (h->type == HOB_TYPE_END_OF_HOB_LIST || h->length < sizeof(*h))
			return 0;
		if (h->type == HOB_TYPE_GUID_EXTENSION &&
		    h->length >= sizeof(*h) + sizeof(struct guid) + sizeof(struct smmstore_info) &&
		    same_guid((const void *)(hob + sizeof(*h)), &smmstore_info_guid))
			return (const void *)(hob + sizeof(*h) + sizeof(struct guid));
		hob += h->length;
	}
	return 0;
}

/* La mappa di ExitBootServices(): le aree riservate con EFI_MEMORY_RUNTIME,
   la memoria libera tra 1 MiB e 1 GiB e la prima area non libera li', il com
   buffer di SMMSTORE (base, dimensione e blocco di info): MMIO con
   EFI_MEMORY_RUNTIME in tutta la sua estensione, o il primo tipo diverso */
static void check_memory_map(uint64_t size, uint64_t descriptor_size,
			     const struct smmstore_info *info)
{
	uint64_t offset, free_bytes = 0, first_start = 0, cb_mmio = 0;
	uint64_t cb_start = info ? info->com_buffer : 0;
	uint64_t cb_end = info ? cb_start + info->com_buffer_size : 0;
	uint32_t reserved_runtime = 0, first_type = 0, cb_other_type = 0;
	int taken = 0, cb_other = 0;

	for (offset = 0; descriptor_size && offset + descriptor_size <= size;
	     offset += descriptor_size) {
		const struct memory_descriptor *d = (const void *)(memory_map + offset);
		uint64_t start = d->physical_start, end = start + (d->number_of_pages << 12);
		uint64_t lo = start > LOW_START ? start : LOW_START;
		uint64_t hi = end < LOW_END ? end : LOW_END;

		if (d->type == EFI_RESERVED_MEMORY_TYPE && (d->attribute & EFI_MEMORY_RUNTIME))
			reserved_runtime++;
		if (start < cb_end && end > cb_start) {
			uint64_t a = start > cb_start ? start : cb_start;
			uint64_t b = end < cb_end ? end : cb_end;

			if (d->type == EFI_MEMORY_MAPPED_IO && (d->attribute & EFI_MEMORY_RUNTIME)) {
				cb_mmio += b - a;
			} else if (!cb_other) {
				cb_other = 1;
				cb_other_type = d->type;
			}
		}
		if (lo >= hi)
			continue;
		if (d->type == EFI_CONVENTIONAL_MEMORY) {
			free_bytes += hi - lo;
		} else if (!taken || start < first_start) {
			taken = 1;
			first_start = start;
			first_type = d->type;
		}
	}
	serial_puts("ouroBIOS slot lock test: memory map: reserved runtime ");
	serial_putu(reserved_runtime);
	serial_puts(", free from 1 MiB to 1 GiB: ");
	serial_putu((uint32_t)(free_bytes >> 20));
	serial_puts(" MiB");
	if (taken) {
		serial_puts(", type ");
		serial_putu(first_type);
		serial_puts(" at ");
		serial_putu((uint32_t)(first_start >> 10));
		serial_puts(" KiB");
	}
	serial_puts("\n");
	serial_puts("ouroBIOS slot lock test: SMMSTORE com buffer: ");
	if (!info) {
		serial_puts("no HOB\n");
		return;
	}
	serial_putu(info->com_buffer_size >> 10);
	serial_puts(" KiB, block ");
	serial_putu(info->block_size >> 10);
	serial_puts(" KiB, runtime MMIO ");
	serial_putu((uint32_t)(cb_mmio >> 10));
	serial_puts(" KiB");
	if (cb_other) {
		serial_puts(", type ");
		serial_putu(cb_other_type);
	}
	serial_puts("\n");
}

static __attribute__((noreturn)) void stop(void)
{
	for (;;)
		__asm__ volatile("cli; hlt");
}

/* prima la risposta, poi la riga: con DEBUG_SMI anche coreboot scrive
   sulla seriale, durante l'SMI */
static void try_other(const char *when)
{
	uint32_t ret = smmstore(SMMSTORE_CMD_VBOOT_TRY_OTHER, smm_param);

	serial_puts("ouroBIOS slot lock test: TRY_OTHER ");
	serial_puts(when);
	serial_puts(" ExitBootServices: ");
	serial_putu(ret);
	serial_puts("\n");
}

efi_status efi_main(void *image, struct system_table *st)
{
	struct boot_services *bs = st->boot_services;
	const struct smmstore_info *info = find_smmstore(st);
	struct smmstore_info copy;
	uint64_t size, key, descriptor_size;
	uint32_t descriptor_version;
	int i;

	/* gli HOB sono dati dei servizi di boot: una copia per dopo */
	if (info) {
		copy = *info;
		info = &copy;
	}
	try_other("before");
	serial_puts("ouroBIOS slot lock test: ExitBootServices()\n");
	for (i = 0; i < 8; i++) {
		size = sizeof(memory_map);
		if (bs->get_memory_map(&size, memory_map, &key, &descriptor_size, &descriptor_version))
			continue;
		if (!bs->exit_boot_services(image, key))
			break;
	}
	if (i == 8) {
		serial_puts("ouroBIOS slot lock test: ExitBootServices() failed\n");
		stop();
	}

	check_memory_map(size, descriptor_size, info);
	try_other("after");
	stop();
}

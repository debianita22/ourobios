/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * lock-probe.c - per la prova LOCK-12 su una macchina (docs/testing.md):
 * un'applicazione UEFI da registrare come voce SysPrep####, cioe' codice che
 * non e' del firmware e che il boot manager avvia prima di ogni voce di
 * boot. Dalla v1.8.0 il payload arma i blocchi di coreboot prima di caricare
 * un'immagine cosi' (edk2/0068) e ne pubblica l'esito in OptionLockStatus,
 * la variabile volatile che fino alla v1.7.0 nasceva solo a ReadyToBoot.
 *
 * Non scrive niente nello store e non chiede niente a coreboot: legge
 * OptionLockStatus e CfrLockAtBoot (GUID delle opzioni di coreboot) come sono
 * mentre gira, e lascia quello che ha letto in una variabile volatile sua,
 * OuroLockProbe, che il sistema operativo rilegge da efivarfs:
 *
 *   od -An -tx8 -j4 /sys/firmware/efi/efivars/OuroLockProbe-6a3f0c1e-7b52-4d0a-9e84-c1d2e3f4a5b6
 *
 * dopo i 4 byte degli attributi (-j4), quattro numeri a 64 bit: l'EFI_STATUS della
 * lettura di OptionLockStatus (0: c'era gia'), il suo valore (0: il blocco
 * delle opzioni armato), l'EFI_STATUS della lettura di CfrLockAtBoot e il suo
 * valore (1: scattato).
 *
 * Nessuna libreria:
 *   clang --target=x86_64-unknown-windows -std=c11 -O2 -ffreestanding \
 *         -fno-stack-protector -mno-red-zone -mgeneral-regs-only -nostdlib \
 *         -fuse-ld=lld -Wl,-subsystem:efi_application -Wl,-entry:efi_main \
 *         -o lock-probe.efi tools/efi/lock-probe.c
 * e le chiamate ai servizi UEFI usano l'ABI di Microsoft, quella di quel target.
 */

#include <stdint.h>

typedef uint64_t efi_status;

struct guid {
	uint32_t data1;
	uint16_t data2, data3;
	uint8_t data4[8];
};

struct table_header {
	uint64_t signature;
	uint32_t revision, header_size, crc32, reserved;
};

/* EFI_RUNTIME_SERVICES fino a SetVariable() (UEFI 2.10, 4.5) */
struct runtime_services {
	struct table_header hdr;
	void *get_time, *set_time, *get_wakeup_time, *set_wakeup_time,
	     *set_virtual_address_map, *convert_pointer;
	efi_status (*get_variable)(const uint16_t *name, const struct guid *vendor,
				   uint32_t *attributes, uint64_t *size, void *data);
	void *get_next_variable_name;
	efi_status (*set_variable)(const uint16_t *name, const struct guid *vendor,
				   uint32_t attributes, uint64_t size, const void *data);
};

/* EFI_SYSTEM_TABLE (UEFI 2.10, 4.3) */
struct system_table {
	struct table_header hdr;
	void *firmware_vendor;
	uint32_t firmware_revision;
	void *console_in_handle, *con_in, *console_out_handle, *con_out,
	     *standard_error_handle, *std_err;
	struct runtime_services *runtime_services;
};

_Static_assert(__builtin_offsetof(struct runtime_services, get_variable) == 0x48, "GetVariable");
_Static_assert(__builtin_offsetof(struct runtime_services, set_variable) == 0x58, "SetVariable");
_Static_assert(__builtin_offsetof(struct system_table, runtime_services) == 0x58, "RuntimeServices");

#define EFI_VARIABLE_BOOTSERVICE_ACCESS	0x2
#define EFI_VARIABLE_RUNTIME_ACCESS	0x4

/* gEficorebootNvDataGuid: le opzioni di coreboot */
static const struct guid coreboot_guid = {
	0xceae4c1d, 0x335b, 0x4685, { 0xa4, 0xa0, 0xfc, 0x4a, 0x94, 0xee, 0xa0, 0x85 }
};
/* la variabile della prova, di nessun altro */
static const struct guid probe_guid = {
	0x6a3f0c1e, 0x7b52, 0x4d0a, { 0x9e, 0x84, 0xc1, 0xd2, 0xe3, 0xf4, 0xa5, 0xb6 }
};

static const uint16_t option_lock_status[] = u"OptionLockStatus";
static const uint16_t cfr_lock_at_boot[] = u"CfrLockAtBoot";
static const uint16_t probe_name[] = u"OuroLockProbe";

efi_status efi_main(void *image, struct system_table *st)
{
	struct runtime_services *rt = st->runtime_services;
	uint64_t result[4] = { 0, ~0ULL, 0, ~0ULL };
	uint64_t size, status = 0;
	uint8_t trigger = 0xff;

	(void)image;
	size = sizeof(status);
	result[0] = rt->get_variable(option_lock_status, &coreboot_guid, 0, &size, &status);
	if (!result[0] && size == sizeof(status))
		result[1] = status;
	size = sizeof(trigger);
	result[2] = rt->get_variable(cfr_lock_at_boot, &coreboot_guid, 0, &size, &trigger);
	if (!result[2] && size == sizeof(trigger))
		result[3] = trigger;
	return rt->set_variable(probe_name, &probe_guid,
				EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS,
				sizeof(result), result);
}

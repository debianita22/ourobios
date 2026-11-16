/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * slot-lock-driver.c - per la prova dell'aggiornamento (tools/qemu-update.py):
 * un driver UEFI, la voce Driver0000 della prova, cioe' codice che non e'
 * del firmware avviato dal boot manager prima di ogni voce di boot, quando
 * il payload non ha ancora bloccato niente da se' (i blocchi li arma a
 * ReadyToBoot). Chiede a coreboot di avviare l'altro slot di vboot
 * (SMMSTORE_CMD_VBOOT_TRY_OTHER, patch 0065), scrive la risposta sulla
 * seriale (COM1) e torna al boot manager. coreboot deve rifiutarlo: il
 * payload arma i blocchi prima di caricare un'immagine che non viene da un
 * firmware volume (edk2/0068), e in un avvio chiesto verso il setup
 * (OsIndications, BOOT_TO_FW_UI) non la carica affatto.
 *
 * Un driver e non un'applicazione come slot-lock-test.c: il boot manager
 * avvia da una voce Driver#### solo un'immagine con il sottosistema dei
 * driver. Nessuna libreria: tools/build.sh lo compila con
 *   clang --target=x86_64-unknown-windows -ffreestanding -nostdlib -fuse-ld=lld
 *         -Wl,-subsystem:efi_boot_service_driver -Wl,-entry:efi_main
 */

#include <stdint.h>

#define COM1				0x3f8
#define APM_CNT				0xb2
#define APM_CNT_SMMSTORE		0xed
#define SMMSTORE_CMD_VBOOT_TRY_OTHER	9

typedef uint64_t efi_status;

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

/* prima la risposta, poi la riga: con DEBUG_SMI anche coreboot scrive
   sulla seriale, durante l'SMI */
efi_status efi_main(void *image, void *system_table)
{
	uint32_t ret = smmstore(SMMSTORE_CMD_VBOOT_TRY_OTHER, smm_param);
	char digit[2] = { (char)('0' + (ret < 10 ? ret : 9)), '\0' };

	(void)image;
	(void)system_table;
	serial_puts("ouroBIOS slot lock test: TRY_OTHER as a Driver option: ");
	serial_puts(digit);
	serial_puts("\n");
	return 0;
}

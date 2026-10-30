/* SPDX-License-Identifier: GPL-2.0-only */

/*
 * tools/cfr-dump.sh: il menu di setup di una board (CFR) costruito sull'host.
 *
 * Questo file si compila come il ramstage, con gli header di coreboot e il
 * config.h della build, e include il cfr.c della mainboard (CFR_DUMP_MB_CFR,
 * passato dallo script): cosi' vede il suo sm_root[], che e' static. Il
 * resto del menu (ec/lenovo/h8/cfr.c, console/cfr.c, drivers/option/cfr.c)
 * sono oggetti a parte, compilati allo stesso modo.
 *
 * Le funzioni che sul W541 leggono l'hardware (CPU, cbmem, VPD, EC) sono qui
 * sotto con valori finti ma plausibili: un i7-4810MQ, 16 GiB, un EC GNHT24WW,
 * e nessun numero di serie vero. Quelle dell'H8 che leggono il devicetree
 * prendono i valori dal static.c della build (-DCFR_DUMP_H8_*).
 *
 *   cfr-dump-bin blob   il record lb_cfr, come lo scrive il ramstage nella
 *                       tabella di coreboot, su stdout
 *   cfr-dump-bin list   l'albero di sm_root[] e delle form generiche, letto
 *                       dalle strutture in memoria (con i ctor), su stdout:
 *                       lo script lo confronta con quello letto dal blob
 */

#include CFR_DUMP_MB_CFR

#include <arch/cbconfig.h>
#include <cbmem.h>
#include <commonlib/memory_info.h>
#include <console/console.h>
#include <console/uart.h>
#include <cpu/x86/name.h>
#include <device/device.h>
#include <device/resource.h>
#include <drivers/option/cfr_frontend.h>
#include <drivers/vpd/vpd.h>
#include <ec/lenovo/h8/h8.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

/* Della libc dell'host, senza i suoi header (qui ci sono quelli di coreboot) */
ssize_t write(int fd, const void *buf, size_t count);
void exit(int status) __noreturn;

#ifndef CFR_DUMP_H8_THINKLIGHT
#define CFR_DUMP_H8_THINKLIGHT		0
#endif
#ifndef CFR_DUMP_H8_KB_BACKLIGHT
#define CFR_DUMP_H8_KB_BACKLIGHT	1
#endif
#ifndef CFR_DUMP_H8_UWB
#define CFR_DUMP_H8_UWB			0
#endif
#ifndef CFR_DUMP_H8_PM_BEEPS
#define CFR_DUMP_H8_PM_BEEPS		0
#endif

static void put(int fd, const char *s, size_t len)
{
	while (len) {
		ssize_t n = write(fd, s, len);
		if (n <= 0)
			exit(2);
		s += n;
		len -= n;
	}
}

/* printk e die: sullo stderr dell'host */
int printk(int msg_level, const char *fmt, ...)
{
	char buf[512];
	va_list ap;
	int len;

	va_start(ap, fmt);
	len = vsnprintf(buf, sizeof(buf), fmt, ap);
	va_end(ap);
	if (len < 0)
		return len;
	if ((size_t)len >= sizeof(buf))
		len = sizeof(buf) - 1;
	put(2, buf, len);
	return len;
}

void die(const char *fmt, ...)
{
	char buf[512];
	va_list ap;
	int len;

	va_start(ap, fmt);
	len = vsnprintf(buf, sizeof(buf), fmt, ap);
	va_end(ap);
	put(2, "cfr-dump: die: ", 15);
	if (len > 0)
		put(2, buf, MIN((size_t)len, sizeof(buf) - 1));
	put(2, "\n", 1);
	exit(1);
}

/* La CPU: il brand string di CPUID, come fill_processor_name() lo lascia */
void fill_processor_name(char *processor_name)
{
	strcpy(processor_name, "Intel(R) Core(TM) i7-4810MQ CPU @ 2.80GHz");
}

/* La memoria: due moduli da 8 GiB DDR3-1600, come li scrive raminit_shared.c */
static struct memory_info fake_meminfo;

void *cbmem_find(u32 id)
{
	if (id != CBMEM_ID_MEMINFO)
		return NULL;
	fake_meminfo.dimm_cnt = 2;
	for (int i = 0; i < 2; i++) {
		fake_meminfo.dimm[i].dimm_size = 8192;		/* MiB */
		fake_meminfo.dimm[i].ddr_frequency = 1600;	/* MT/s */
		fake_meminfo.dimm[i].channel_num = i;
	}
	return &fake_meminfo;
}

/* Il VPD: dati di esempio, non quelli di una macchina vera */
static const struct {
	const char *key;
	const char *value;
} fake_vpd[] = {
	{ "system_product_name",	"20EFCTO1WW"	},
	{ "serial_number",		"PC0EXAMPLE"	},
	{ "mlb_serial_number",		"L1EXAMPLE00000" },
};

static const uint8_t fake_uuid[16] = {
	0x2e, 0x1c, 0x9a, 0x5b, 0x6d, 0x4f, 0x8a, 0x4e,
	0x9c, 0x3b, 0x7d, 0x2e, 0x1f, 0x0a, 0x6b, 0x4c,
};

char *vpd_gets(const char *key, char *buffer, int size, enum vpd_region region)
{
	for (size_t i = 0; i < ARRAY_SIZE(fake_vpd); i++) {
		if (strcmp(key, fake_vpd[i].key) || size <= 0)
			continue;
		strncpy(buffer, fake_vpd[i].value, size - 1);
		buffer[size - 1] = '\0';
		return buffer;
	}
	return NULL;
}

const void *vpd_find(const char *key, int *size, enum vpd_region region)
{
	if (strcmp(key, "system_uuid"))
		return NULL;
	*size = sizeof(fake_uuid);
	return fake_uuid;
}

/* L'EC H8: la versione, poi quello che il devicetree e l'EC dicono */
u8 h8_build_id_and_function_spec_version(char *buf, u8 buf_len)
{
	static const char version[] = "GNHT24WW-1.0";
	u8 len = MIN((size_t)buf_len, strlen(version));

	memcpy(buf, version, len);
	return len;
}

bool h8_has_bdc(void)
{
	return true;
}

bool h8_has_wwan(void)
{
	return true;
}

bool h8_has_thinklight(void)
{
	return CFR_DUMP_H8_THINKLIGHT;
}

bool h8_kb_backlight_supported(void)
{
	return CFR_DUMP_H8_KB_BACKLIGHT;
}

u8 h8_illumination_default(void)
{
	if (h8_has_thinklight() && h8_kb_backlight_supported())
		return KIC_BOTH;
	if (h8_has_thinklight())
		return KIC_THINKLIGHT;
	if (h8_kb_backlight_supported())
		return KIC_KEYBOARD;
	return KIC_NONE;
}

bool h8_has_uwb(void)
{
	return CFR_DUMP_H8_UWB;
}

bool h8_has_power_management_beeps(void)
{
	return CFR_DUMP_H8_PM_BEEPS;
}

/*
 * La console seriale con CONSOLE_SERIAL_RUNTIME: console/cfr.c mostra "Serial
 * Console" se un dispositivo PNP acceso del devicetree ha la porta della UART
 * della console. Qui una UART come quella del M920x (COM1 del Super I/O,
 * 0x3f8): l'opzione si vede come sulla macchina.
 */
#define CFR_DUMP_UART_BASE	0x3f8

uintptr_t uart_platform_base(unsigned int idx)
{
	return idx == 0 ? CFR_DUMP_UART_BASE : 0;
}

static struct resource console_uart_res = {
	.base	= CFR_DUMP_UART_BASE,
	.flags	= IORESOURCE_IO,
};

static struct device console_uart_dev = {
	.path		= { .type = DEVICE_PATH_PNP },
	.enabled	= 1,
	.resource_list	= &console_uart_res,
};

bool is_dev_enabled(const struct device *dev)
{
	return dev && dev->enabled;
}

DEVTREE_CONST struct device *dev_find_path(DEVTREE_CONST struct device *prev_match,
					   enum device_path_type path_type)
{
	return !prev_match && path_type == DEVICE_PATH_PNP ? &console_uart_dev : NULL;
}

/*
 * L'elenco di riferimento: sm_root[] e le form generiche lette dalle
 * strutture, con i ctor applicati a una copia come fa drivers/option/cfr.c.
 * Una riga per oggetto, indentata di due spazi per livello:
 *   <tipo> <opt_name o -> "<ui_name>"[ dep=<opt_name>[valori]][ {nome=valore|...}]
 * Lo script scrive lo stesso elenco dal blob e confronta i due.
 */
extern struct sm_obj_form __start_cfr_forms[];
extern struct sm_obj_form __stop_cfr_forms[];

static char out[1 << 20];
static size_t out_len;

static void __printf(1, 2) out_printf(const char *fmt, ...)
{
	va_list ap;
	int len;

	va_start(ap, fmt);
	len = vsnprintf(out + out_len, sizeof(out) - out_len, fmt, ap);
	va_end(ap);
	if (len < 0 || (size_t)len >= sizeof(out) - out_len)
		die("list: more than %zu bytes", sizeof(out));
	out_len += len;
}

static const char *opt_name_of(const struct sm_object *obj)
{
	switch (obj->kind) {
	case SM_OBJ_ENUM:	return obj->sm_enum.opt_name;
	case SM_OBJ_NUMBER:	return obj->sm_number.opt_name;
	case SM_OBJ_BOOL:	return obj->sm_bool.opt_name;
	case SM_OBJ_VARCHAR:	return obj->sm_varchar.opt_name;
	default:		return "-";
	}
}

static void list_form(const struct sm_obj_form *form, int depth, const struct sm_object *obj);

static void list_object(const struct sm_object *orig, int depth)
{
	struct sm_object obj = *orig;
	const char *ui_name;

	if (orig->ctor)
		orig->ctor(&obj);

	switch (obj.kind) {
	case SM_OBJ_NONE:
		return;
	case SM_OBJ_FORM:
		list_form(&obj.sm_form, depth, &obj);
		return;
	case SM_OBJ_ENUM:	ui_name = obj.sm_enum.ui_name;		break;
	case SM_OBJ_NUMBER:	ui_name = obj.sm_number.ui_name;	break;
	case SM_OBJ_BOOL:	ui_name = obj.sm_bool.ui_name;		break;
	case SM_OBJ_VARCHAR:	ui_name = obj.sm_varchar.ui_name;	break;
	case SM_OBJ_COMMENT:	ui_name = obj.sm_comment.ui_name;	break;
	default:
		die("list: object of kind %u", obj.kind);
	}

	static const char *const kinds[] = {
		[SM_OBJ_ENUM] = "enum", [SM_OBJ_NUMBER] = "number", [SM_OBJ_BOOL] = "bool",
		[SM_OBJ_VARCHAR] = "varchar", [SM_OBJ_COMMENT] = "comment",
	};
	out_printf("%*s%s %s \"%s\"", depth * 2, "", kinds[obj.kind], opt_name_of(&obj), ui_name);
	if (obj.dep && (obj.dep->kind == SM_OBJ_BOOL || obj.dep->kind == SM_OBJ_ENUM)) {
		out_printf(" dep=%s", opt_name_of(obj.dep));
		if (obj.dep_values && obj.num_dep_values) {
			for (uint32_t i = 0; i < obj.num_dep_values; i++)
				out_printf("%c%u", i ? ',' : '[', obj.dep_values[i]);
			out_printf("]");
		}
	}
	if (obj.kind == SM_OBJ_ENUM && obj.sm_enum.values) {
		for (const struct sm_enum_value *e = obj.sm_enum.values; e->ui_name; e++)
			out_printf("%s%s=%u", e == obj.sm_enum.values ? " {" : "|", e->ui_name, e->value);
		if (obj.sm_enum.values->ui_name)
			out_printf("}");
	}
	out_printf("\n");
}

static void list_form(const struct sm_obj_form *form, int depth, const struct sm_object *obj)
{
	out_printf("%*sform - \"%s\"", depth * 2, "", form->ui_name);
	if (obj && obj->dep && (obj->dep->kind == SM_OBJ_BOOL || obj->dep->kind == SM_OBJ_ENUM)) {
		out_printf(" dep=%s", opt_name_of(obj->dep));
		if (obj->dep_values && obj->num_dep_values) {
			for (uint32_t i = 0; i < obj->num_dep_values; i++)
				out_printf("%c%u", i ? ',' : '[', obj->dep_values[i]);
			out_printf("]");
		}
	}
	out_printf("\n");
	for (size_t i = 0; form->obj_list[i]; i++)
		list_object(form->obj_list[i], depth + 1);
}

/* Il record, in un buffer ben piu' grande della tabella di coreboot */
static union {
	struct lb_cfr root;
	char raw[1 << 20];
} blob;

int main(int argc, char **argv)
{
	if (argc == 2 && !strcmp(argv[1], "blob")) {
		mb_cfr_setup_menu(&blob.root);
		if (blob.root.tag != LB_TAG_CFR_ROOT || blob.root.size < sizeof(blob.root) ||
		    blob.root.size > sizeof(blob.raw))
			die("blob: no valid lb_cfr record (tag 0x%x, size %u)",
			    blob.root.tag, blob.root.size);
		if (blob.root.size > COREBOOT_TABLE_SIZE)
			printk(BIOS_ERR, "cfr-dump: the record (%u bytes) is larger than the whole "
			       "coreboot table (%u bytes)\n", blob.root.size, COREBOOT_TABLE_SIZE);
		put(1, blob.raw, blob.root.size);
		return 0;
	}
	if (argc == 2 && !strcmp(argv[1], "list")) {
		for (size_t i = 0; sm_root[i]; i++)
			list_form(sm_root[i], 0, NULL);
		for (struct sm_obj_form *f = __start_cfr_forms; f != __stop_cfr_forms; f++)
			list_form(f, 0, NULL);
		put(1, out, out_len);
		return 0;
	}
	put(2, "usage: cfr-dump-bin blob|list\n", 30);
	return 2;
}

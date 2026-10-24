#!/usr/bin/env python3
# ddr-report.py - il controller della memoria del W541 (Haswell) come l'ha
# lasciato la RAM init: mrc.bin (variante mrc) o quella nativa di coreboot
# (nri). Frequenza e tensione, DIMM, timing e turnaround, comando 1N/2N, le
# latenze di andata e ritorno per rank, i ritardi CLK/CMD/CTL, e per ogni
# byte di ogni rank i ritardi e le Vref dell'addestramento; comp, ODT,
# equalizzazione e slew rate dell'I/O.
#
#   sudo python3 tools/ddr-report.py                       # il rapporto, dai registri
#   sudo python3 tools/ddr-report.py --save mrc.txt        # e il dump dei registri
#   python3 tools/ddr-report.py --file mrc.txt             # il rapporto da un dump
#   python3 tools/ddr-report.py --compare mrc.txt nri.txt  # solo quello che cambia
#
# Lo scopo e' il confronto tra le due varianti sulla stessa macchina e con le
# stesse DIMM: quello che il training di mrc.bin ottiene e la nri no (i passi
# che le mancano, docs/raminit.md). Un dump per variante, dopo un avvio
# completo, poi --compare. I valori dell'addestramento cambiano un poco da un
# avvio a freddo all'altro anche con lo stesso firmware.
#
# Legge l'MCHBAR (base nel registro 0x48 di 0:0.0) da /dev/mem, 4 byte alla
# volta e solo in lettura, nelle zone del controller di memoria. Il layout dei
# campi viene da reg_structs.h e mchbar.h di coreboot 26.09-280
# (src/northbridge/intel/haswell/), gli stessi della nri. Solo la libreria
# standard di Python.
import argparse
import mmap
import os
import sys
import time

MCHBAR_SIZE = 0x8000
# Le zone lette: I/O DDR per byte e per canale, CKE/CMD/CLK/CTL, scrambler,
# comp globale; del MC per canale solo timing, latenze e refresh (non il REUT
# ne' l'accesso ai buffer, LDAT); power down, decodifica degli indirizzi,
# potenza e tensione della DDR, frequenza
RANGES = [(0x0000, 0x1000), (0x1200, 0x1e00), (0x2000, 0x200c), (0x3a00, 0x3a28)]
for _mc in (0x000, 0x400):
    RANGES += [(0x4000 + _mc, 0x4030 + _mc), (0x40d0 + _mc, 0x40d4 + _mc),
               (0x4290 + _mc, 0x42a8 + _mc), (0x4328 + _mc, 0x432c + _mc)]
RANGES += [(0x4cb0, 0x4cb4), (0x5000, 0x5100), (0x5880, 0x58f0), (0x5e00, 0x5e08)]
DUMP_MAGIC = "# ddr-report dump 1"

# Dai union di reg_structs.h: (campo, bit piu' basso, larghezza[, con segno])
FIELDS = {
    'ddr_data_rx_train_rank': [('rcven', 0, 9), ('dqs_p', 9, 6), ('rx_eq', 15, 5),
        ('dqs_n', 20, 6), ('vref', 26, 6, 1)],
    'ddr_data_tx_train_rank': [('dq_delay', 0, 9), ('dqs_delay', 9, 9), ('tx_eq', 20, 6)],
    'ddr_data_offset_comp': [('drv_up', 0, 6, 1), ('drv_down', 6, 6, 1), ('odt_up', 12, 5, 1),
        ('odt_down', 17, 5, 1), ('t_clk_out', 22, 5, 1), ('slew_rate', 27, 5, 1)],
    'ddr_data_offset_train': [('rcven', 0, 6, 1), ('rx_dqs', 6, 6, 1), ('tx_dq', 12, 6, 1),
        ('tx_dqs', 18, 6, 1), ('vref', 24, 7, 1)],
    'ddr_data_control_0': [('rx_training_mode', 0, 1), ('wl_training_mode', 1, 1),
        ('rl_training_mode', 2, 1), ('samp_train_mode', 3, 1), ('tx_on', 4, 1),
        ('rf_on', 5, 1), ('rx_pi_on', 6, 1), ('tx_pi_on', 7, 1), ('internal_clocks_on', 8, 1),
        ('repeater_clocks_on', 9, 1), ('tx_disable', 10, 1), ('rx_disable', 11, 1),
        ('tx_long', 12, 1), ('rx_dqs_ctle', 13, 2), ('rx_read_pointer', 15, 3),
        ('driver_segment_enable', 18, 1), ('data_vccddq_hi', 19, 1), ('read_rf_rd', 20, 1),
        ('read_rf_wr', 21, 1), ('read_rf_rank', 22, 2), ('force_odt_on', 24, 1),
        ('odt_samp_off', 25, 1), ('disable_odt_static', 26, 1), ('ddr_cr_force_odt_on', 27, 1),
        ('lpddr_mode', 28, 1), ('en_read_preamble', 29, 1), ('odt_samp_extend_en', 30, 1),
        ('early_rleak_en', 31, 1)],
    'ddr_data_control_1': [('ref_pi', 0, 4, 1), ('dll_mask', 4, 2), ('dll_weaklock', 6, 1),
        ('sdll_segment_disable', 7, 3), ('rx_bias_ctl', 10, 3), ('odt_delay', 13, 4, 1),
        ('odt_duration', 17, 3), ('sense_amp_delay', 20, 4, 1), ('sense_amp_duration', 24, 3),
        ('burst_end_odt_delay', 27, 3), ('lpddr_long_odt_en', 30, 1)],
    'ddr_data_control_2': [('rx_stagger_ctl', 0, 5), ('force_bias_on', 5, 1),
        ('force_rx_on', 6, 1), ('leaker_comp', 7, 2), ('rx_dqs_amp_offset', 9, 4),
        ('rx_clk_stg_num', 13, 5), ('wl_long_delay', 18, 1), ('enable_vref_pwrdn', 19, 1),
        ('ddr4_mode', 20, 1), ('en_vddq_odt', 21, 1), ('en_vtt_odt', 22, 1),
        ('en_const_z_eq_tx', 23, 1), ('tx_eq_dis', 24, 1), ('rx_vref_prog_mfc', 25, 1),
        ('cben', 26, 3), ('tx_deskew_disable', 29, 1), ('rx_deskew_disable', 30, 1),
        ('dq_slew_dly_byp', 31, 1)],
    'ddr_data_comp_0': [('rcomp_drv_up', 0, 6), ('rcomp_drv_down', 9, 6), ('vt_comp', 15, 5),
        ('tco_comp', 20, 6), ('slew_rate_comp', 26, 5)],
    'ddr_data_comp_1': [('rcomp_odt_up', 0, 6), ('rcomp_odt_down', 9, 6),
        ('panic_drv_down', 16, 6), ('panic_drv_up', 22, 6), ('ls_comp', 28, 3)],
    'ddr_comp_cmd_comp': [('slew_rate_comp', 0, 6), ('tco_comp', 6, 6),
        ('rcomp_drv_up', 12, 6), ('rcomp_drv_down', 18, 6), ('ls_comp', 24, 3)],
    'ddr_comp_ctl_comp': [('slew_rate_comp', 0, 6), ('tco_comp', 6, 6),
        ('rcomp_drv_up', 12, 6), ('rcomp_drv_down', 18, 6), ('ls_comp', 24, 4)],
    'ddr_comp_clk_comp': [('slew_rate_comp', 0, 5), ('tco_comp', 5, 6),
        ('rcomp_drv_up', 11, 6), ('rcomp_drv_down', 17, 6), ('ls_comp', 23, 4)],
    'ddr_comp_ctl_0': [('disable_odt_static', 3, 1), ('odt_up_down_off', 4, 6),
        ('fixed_odt_offset', 10, 1), ('dq_drv_vref', 11, 4, 1), ('dq_odt_vref', 15, 5, 1),
        ('cmd_drv_vref', 20, 4, 1), ('ctl_drv_vref', 24, 4, 1), ('clk_drv_vref', 28, 4, 1)],
    'ddr_comp_ctl_1': [('dq_scomp', 0, 5), ('cmd_scomp', 5, 5), ('ctl_scomp', 10, 5),
        ('clk_scomp', 15, 5), ('tco_cmd_offset', 20, 4), ('comp_clk_on', 24, 1),
        ('vccddq_hi', 25, 1), ('dis_quick_comp', 29, 1), ('sin_step', 30, 1),
        ('sin_step_adv', 31, 1)],
    'ddr_data_vref_adjust': [('vref_ca_ctrl', 0, 7, 1), ('vref_dq_ch1_ctrl', 7, 7, 1),
        ('vref_dq_ch0_ctrl', 14, 7, 1), ('en_dimm_vref_ca', 21, 1),
        ('en_dimm_vref_ch1', 22, 1), ('en_dimm_vref_ch0', 23, 1), ('hi_z_timer_ctrl', 24, 2),
        ('vccddq_hi_qnnn_h', 26, 1), ('ca_slow_bw', 29, 1), ('ch0_slow_bw', 30, 1),
        ('ch1_slow_bw', 31, 1)],
    'ddr_comp_vsshi': [('panic_drv_down_vref', 0, 6), ('panic_drv_up_vref', 6, 6),
        ('vt_offset', 12, 5), ('vt_slope_a', 17, 3), ('vt_slope_b', 20, 3)],
    'ddr_comp_vsshi_control': [('vsshi_target', 0, 6), ('hi_bw_divider', 6, 2),
        ('lo_bw_divider', 8, 2), ('sample_divider', 10, 3), ('open_loop', 13, 1),
        ('bw_error', 14, 2), ('panic_driver_en', 16, 1), ('panic_voltage', 18, 4),
        ('gain_boost', 22, 1), ('sel_code', 23, 1), ('output_code', 24, 8)],
    'clk_pi_code': [('pi_0', 0, 7), ('pi_1', 7, 7), ('pi_2', 14, 7), ('pi_3', 21, 7)],
    'ctl_pi_code': [('pi_0', 0, 7), ('pi_1', 7, 7), ('pi_2', 14, 7), ('pi_3', 21, 7),
        ('xover_en', 28, 1)],
    'cmd_pi_code': [('pi_0', 0, 7), ('pi_1', 7, 7)],
    'ddr_clk_controls': [('ref_pi', 0, 4), ('dll_mask', 4, 2), ('tx_on', 7, 1),
        ('internal_clocks_on', 8, 1), ('repeater_clocks_on', 9, 1), ('io_lb_ctl', 10, 2),
        ('odt_mode', 12, 1), ('rx_vref', 21, 6), ('vccddq_hi', 27, 1), ('dll_weaklock', 28, 1),
        ('lpddr_mode', 29, 1)],
    'ddr_cmd_controls': [('ref_pi', 0, 4, 1), ('dll_mask', 4, 2), ('tx_on', 7, 1),
        ('internal_clocks_on', 8, 1), ('repeater_clocks_on', 9, 1), ('io_lb_ctl', 10, 2),
        ('odt_mode', 12, 1), ('cmd_tx_eq', 13, 2), ('early_weak_drive', 15, 2),
        ('rx_vref', 21, 6, 1), ('vccddq_hi', 27, 1), ('dll_weaklock', 28, 1),
        ('lpddr_mode', 29, 1), ('lpddr_ca_a_dis', 30, 1), ('lpddr_ca_b_dis', 31, 1)],
    'ddr_cke_ctl_controls': [('ref_pi', 0, 4, 1), ('dll_mask', 4, 2), ('tx_on', 7, 1),
        ('internal_clocks_on', 8, 1), ('repeater_clocks_on', 9, 1), ('io_lb_ctl', 10, 2),
        ('odt_mode', 12, 1), ('cmd_tx_eq', 13, 2), ('early_weak_drive', 15, 2),
        ('ctl_tx_eq', 17, 2), ('ctl_sr_drv', 19, 2), ('rx_vref', 21, 6, 1),
        ('vccddq_hi', 27, 1), ('dll_weaklock', 28, 1), ('lpddr_mode', 29, 1),
        ('la_drv_en_ovrd', 30, 1), ('lpddr_ca_a_dis', 31, 1)],
    'sc_roundt_lat': [('R0D0', 0, 6), ('R1D0', 8, 6), ('R0D1', 16, 6), ('R1D1', 24, 6)],
    'sc_io_latency': [('iolat_rank0', 0, 4), ('iolat_rank1', 4, 4), ('iolat_rank2', 8, 4),
        ('iolat_rank3', 12, 4), ('rt_iocomp', 16, 6), ('dis_rt_clk_gate', 31, 1)],
    'tc_bank': [('tRCD', 0, 5), ('tRP', 5, 5), ('tRAS', 10, 6), ('tRDPRE', 16, 4),
        ('tWRPRE', 20, 6), ('tRRD', 26, 4), ('tRPab_ext', 30, 2)],
    'tc_bank_rank_a': [('tCKE', 0, 4), ('tFAW', 4, 8), ('tRDRD_sr', 12, 3),
        ('tRDRD_dr', 15, 4), ('tRDRD_dd', 19, 4), ('tRDPDEN', 23, 5), ('cmd_3st_dis', 29, 1),
        ('cmd_stretch', 30, 2)],
    'tc_bank_rank_b': [('tWRRD_sr', 0, 6), ('tWRRD_dr', 6, 4), ('tWRRD_dd', 10, 4),
        ('tWRWR_sr', 14, 3), ('tWRWR_dr', 17, 4), ('tWRWR_dd', 21, 4), ('tWRPDEN', 25, 6),
        ('dec_wrd', 31, 1)],
    'tc_bank_rank_c': [('tXPDLL', 0, 6), ('tXP', 6, 4), ('tAONPD', 10, 4), ('tRDWR_sr', 14, 5),
        ('tRDWR_dr', 19, 5), ('tRDWR_dd', 24, 5)],
    'tc_bank_rank_d': [('tAA', 0, 5), ('tCWL', 5, 5), ('tCPDED', 10, 2), ('tPRPDEN', 12, 2),
        ('odt_read_delay', 14, 3), ('odt_read_duration', 17, 2), ('odt_write_duration', 19, 3),
        ('odt_write_delay', 22, 3), ('odt_always_rank_0', 25, 1), ('cmd_delay', 26, 2)],
    'tc_rftp': [('tREFI', 0, 16), ('tRFC', 16, 9), ('tREFIx9', 25, 7)],
    'tc_srftp': [('tXSDLL', 0, 12), ('tXS_offset', 12, 4), ('tZQOPER', 16, 10),
        ('tMOD', 28, 4)],
    'tc_mr2_shadow': [('mr2_shadow_low', 0, 6), ('srt_available', 6, 2),
        ('mr2_shadow_high', 8, 3), ('addr_bit_swizzle', 14, 2)],
    'mcmain_command_rate_limit': [('enable_cmd_limit', 0, 1), ('cmd_rate_limit', 1, 3),
        ('reset_on_command', 4, 4), ('reset_delay', 8, 4), ('ck_to_cke_delay', 12, 2),
        ('init_mrw_2n_cs', 31, 1)],
    'mad_chnl': [('ch_a', 0, 2), ('ch_b', 2, 2), ('ch_c', 4, 2), ('stacked_mode', 6, 1),
        ('stkd_mode_bits', 7, 3), ('lpddr_mode', 10, 1)],
    'mad_dimm': [('dimm_a_size', 0, 8), ('dimm_b_size', 8, 8), ('dimm_a_sel', 16, 1),
        ('dimm_a_ranks', 17, 1), ('dimm_b_ranks', 18, 1), ('dimm_a_width', 19, 1),
        ('dimm_b_width', 20, 1), ('rank_interleave', 21, 1), ('enh_interleave', 22, 1),
        ('ecc_io_on', 24, 1), ('ecc_logic_on', 25, 1), ('hori_mode', 26, 1),
        ('hori_address', 27, 3)],
    'mad_zr': [('ch_b_double', 16, 8), ('ch_b_single', 24, 8)],
    'channel_hash': [('addr_mask', 0, 14), ('lsb_mask_bit', 21, 2), ('enable', 23, 1)],
    'pcu_comp': [('comp_disable', 0, 1), ('comp_interval', 1, 4), ('comp_force', 8, 1)],
    'ddr_scramble': [('scram_en', 0, 1), ('scram_key', 1, 16), ('clk_gate_ab', 17, 2),
        ('clk_gate_c', 19, 2), ('en_dbi_ab', 21, 1)],
}

CHANNELS, RANKS, BYTES = 2, 4, 8


def field(raw, f):
    v = (raw >> f[1]) & ((1 << f[2]) - 1)
    if len(f) > 3 and f[3] and v & (1 << (f[2] - 1)):
        v -= 1 << f[2]
    return v


def decode(raw, union):
    return {f[0]: field(raw, f) for f in FIELDS[union]}


def registers():
    """(nome, offset, union o None) dei registri decodificati, da mchbar.h."""
    out = [("MAD_CHNL", 0x5000, "mad_chnl"), ("MAD_ZR", 0x5014, "mad_zr"),
           ("CHANNEL_HASH", 0x5024, "channel_hash"), ("MRC_REVISION", 0x5034, None),
           ("PM_SREF_CONFIG", 0x5060, None), ("PM_PDWN_CONFIG", 0x4cb0, None),
           ("PCU_DDR_PTM_CTL", 0x5880, None), ("PCU_DDR_RAPL_0x5884", 0x5884, None),
           ("PCU_DDR_RAPL_0x5888", 0x5888, None), ("PCU_DDR_VOLTAGE", 0x58a4, None),
           ("DDR_POWER_LIMIT", 0x58e0, None), ("MC_BIOS_REQ", 0x5e00, None),
           ("MC_BIOS_DATA", 0x5e04, None),
           ("DATA_COMP_0", 0x3a00, "ddr_data_comp_0"), ("DATA_COMP_1", 0x3a04, "ddr_data_comp_1"),
           ("CMD_COMP", 0x3a08, "ddr_comp_cmd_comp"), ("CTL_COMP", 0x3a0c, "ddr_comp_ctl_comp"),
           ("CLK_COMP", 0x3a10, "ddr_comp_clk_comp"), ("COMP_CTL_0", 0x3a14, "ddr_comp_ctl_0"),
           ("COMP_CTL_1", 0x3a18, "ddr_comp_ctl_1"), ("COMP_VSSHI", 0x3a1c, "ddr_comp_vsshi"),
           ("COMP_VSSHI_CONTROL", 0x3a24, "ddr_comp_vsshi_control"),
           ("VREF_ADJUST", 0x0078, "ddr_data_vref_adjust")]
    for ch in range(CHANNELS):
        c, mc, io = "C%d " % ch, 0x400 * ch, 0x100 * ch
        out += [(c + "MAD_DIMM", 0x5004 + 4 * ch, "mad_dimm"),
                (c + "TC_BANK", 0x4000 + mc, "tc_bank"),
                (c + "TC_BANK_RANK_A", 0x4004 + mc, "tc_bank_rank_a"),
                (c + "TC_BANK_RANK_B", 0x4008 + mc, "tc_bank_rank_b"),
                (c + "TC_BANK_RANK_C", 0x400c + mc, "tc_bank_rank_c"),
                (c + "COMMAND_RATE_LIMIT", 0x4010 + mc, "mcmain_command_rate_limit"),
                (c + "TC_BANK_RANK_D", 0x4014 + mc, "tc_bank_rank_d"),
                (c + "SC_ROUNDT_LAT", 0x4024 + mc, "sc_roundt_lat"),
                (c + "SC_IO_LATENCY", 0x4028 + mc, "sc_io_latency"),
                (c + "SC_WR_ADD_DELAY", 0x40d0 + mc, None),
                (c + "TC_ZQCAL", 0x4290 + mc, None),
                (c + "TC_RFP", 0x4294 + mc, None),
                (c + "TC_RFTP", 0x4298 + mc, "tc_rftp"),
                (c + "TC_MR2_SHADOW", 0x429c + mc, "tc_mr2_shadow"),
                (c + "TC_SRFTP", 0x42a4 + mc, "tc_srftp"),
                (c + "PM_THRT_CKE_MIN", 0x4328 + mc, None),
                (c + "CLK_PI", 0x180c + io, "clk_pi_code"),
                (c + "CLK_CONTROLS", 0x1810 + io, "ddr_clk_controls"),
                (c + "CTL_PI", 0x1c18 + io, "ctl_pi_code"),
                (c + "CTL_CONTROLS", 0x1c1c + io, "ddr_cke_ctl_controls"),
                (c + "CKE_CTL_PI", 0x1218 + io, "ctl_pi_code"),
                (c + "CKE_CMD_PI", 0x1208 + io, "cmd_pi_code"),
                (c + "CMD_N_PI", 0x1408 + io, "cmd_pi_code"),
                (c + "CMD_N_CONTROLS", 0x140c + io, "ddr_cmd_controls"),
                (c + "CMD_S_PI", 0x1a08 + io, "cmd_pi_code"),
                (c + "CMD_S_CONTROLS", 0x1a0c + io, "ddr_cmd_controls"),
                (c + "CMD_N_COMP_OFFSET", 0x1404 + io, None),
                (c + "CMD_S_COMP_OFFSET", 0x1a04 + io, None),
                (c + "CTL_COMP_OFFSET", 0x1c14 + io, None),
                (c + "CLK_COMP_OFFSET", 0x1808 + io, None),
                (c + "CKE_CMD_COMP_OFFSET", 0x1204 + io, None),
                (c + "CKE_CTL_COMP_OFFSET", 0x1214 + io, None)]
        for b in range(BYTES):
            cb, db = "C%d.B%d " % (ch, b), io + 0x200 * b
            out += [(cb + "DATA_OFFSET_COMP", 0x005c + db, "ddr_data_offset_comp"),
                    (cb + "DATA_OFFSET_TRAIN", 0x0070 + db, "ddr_data_offset_train"),
                    (cb + "DQ_CONTROL_0", 0x0074 + db, "ddr_data_control_0"),
                    (cb + "DQ_CONTROL_1", 0x0060 + db, "ddr_data_control_1"),
                    (cb + "DQ_CONTROL_2", 0x0064 + db, "ddr_data_control_2"),
                    (cb + "RCOMP_DATA_1", 0x0044 + db, "ddr_data_comp_1"),
                    (cb + "RX_OFFSET_VDQ", 0x004c + db, None),
                    (cb + "DATA_TX_XTALK", 0x0048 + db, None)]
            for r in range(RANKS):
                cr = "C%d.R%d.B%d " % (ch, r, b)
                out += [(cr + "RX_TRAIN", 0x0000 + db + 4 * r, "ddr_data_rx_train_rank"),
                        (cr + "TX_TRAIN", 0x0020 + db + 4 * r, "ddr_data_tx_train_rank"),
                        (cr + "RX_PER_BIT", 0x0010 + db + 4 * r, None),
                        (cr + "TX_PER_BIT", 0x0030 + db + 4 * r, None)]
    return out


# --- lettura -----------------------------------------------------------------

def read_mchbar():
    with open("/sys/bus/pci/devices/0000:00:00.0/config", "rb") as f:
        cfg = f.read(0x50)
    vendor = int.from_bytes(cfg[0:2], "little")
    lo, hi = int.from_bytes(cfg[0x48:0x4c], "little"), int.from_bytes(cfg[0x4c:0x50], "little")
    if vendor != 0x8086 or not lo & 1:
        raise SystemExit("0:0.0 non e' un host bridge Intel con l'MCHBAR attivo")
    base = ((hi << 32) | lo) & 0x7ffffff8000
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    try:
        m = mmap.mmap(fd, MCHBAR_SIZE, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
    finally:
        os.close(fd)
    # un elemento alla volta: una lettura a 32 bit allineata per registro
    words = memoryview(m).cast("I")
    regs = {}
    for start, end in RANGES:
        for off in range(start, end, 4):
            regs[off] = words[off // 4]
    words.release()
    m.close()
    return base, regs


def read_text(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return "?"


def save(path, base, regs):
    with open(path, "w") as f:
        f.write("%s\n# firmware: %s\n# data: %s\n# mchbar: 0x%x\n" % (
            DUMP_MAGIC, read_text("/sys/class/dmi/id/bios_version"),
            time.strftime("%Y-%m-%d %H:%M:%S"), base))
        for off in sorted(regs):
            f.write("0x%04x 0x%08x\n" % (off, regs[off]))


def load(path):
    regs, info = {}, {}
    with open(path) as f:
        lines = f.read().splitlines()
    if not lines or lines[0] != DUMP_MAGIC:
        raise SystemExit("%s: non e' un dump di ddr-report.py --save" % path)
    for line in lines[1:]:
        if line.startswith("# "):
            k, _, v = line[2:].partition(": ")
            info[k] = v
        elif line.strip():
            off, val = line.split()
            regs[int(off, 16)] = int(val, 16)
    return info, regs


# --- valori ------------------------------------------------------------------

def values(regs):
    """Tutti i campi decodificati, nome -> valore; i registri senza union, interi."""
    out = {}
    for name, off, union in registers():
        if off not in regs:
            continue
        if union:
            for k, v in decode(regs[off], union).items():
                out["%s.%s" % (name, k)] = v
        else:
            out[name] = regs[off]
    return out


CMD_RATE = {0: "1N", 2: "2N", 3: "3N"}
VOLTAGE = {0: "1.5 V", 1: "1.35 V", 3: "1.2 V"}


def ddr_clock(v):
    """(MHz del clock DDR, MHz del clock di riferimento), come raminit_shared.c."""
    refclk = 100000 if v["MC_BIOS_REQ"] & 0x10 else 133333
    return ((v["MC_BIOS_DATA"] & 0xf) * refclk + 500) // 1000, (refclk + 500) // 1000


def dimms(v, ch):
    out = []
    for slot in "ab":
        size = v["C%d MAD_DIMM.dimm_%s_size" % (ch, slot)] * 256
        if size:
            ranks = 2 if v["C%d MAD_DIMM.dimm_%s_ranks" % (ch, slot)] else 1
            out.append("%d GiB %s rank" % (size // 1024, "dual" if ranks == 2 else "single"))
    return out


def ranks_present(v, ch):
    present = []
    for slot, r0 in (("a", 0), ("b", 2)):
        if v["C%d MAD_DIMM.dimm_%s_size" % (ch, slot)]:
            present += [r0, r0 + 1] if v["C%d MAD_DIMM.dimm_%s_ranks" % (ch, slot)] else [r0]
    return present


def row(label, cells, width=10):
    return "  %-26s" % label + "".join(("%" + str(width) + "s") % c for c in cells)


def header(title, chs):
    return "\n%-28s" % title + "".join("%10s" % ("C%d" % ch) for ch in chs)


def report(v, info, out):
    mhz, refclk = ddr_clock(v)
    print("%s, MCHBAR %s" % (info.get("firmware", "?"), info.get("mchbar", "?")), file=out)
    print("DDR3-%d (%d MHz, refclk %d MHz), %s" % (
        2 * mhz, mhz, refclk, VOLTAGE.get(v["PCU_DDR_VOLTAGE"] & 7, "0x%x" % v["PCU_DDR_VOLTAGE"])),
        file=out)
    for ch in range(CHANNELS):
        print("C%d: %s" % (ch, ", ".join(dimms(v, ch)) or "vuoto"), file=out)
    chs = [ch for ch in range(CHANNELS) if dimms(v, ch)]

    print(header("Timing (clock DDR)", chs), file=out)
    g = lambda ch, reg, f: v["C%d %s.%s" % (ch, reg, f)]
    print(row("comando", [CMD_RATE.get(g(ch, "TC_BANK_RANK_A", "cmd_stretch"), "?") for ch in chs]),
          file=out)
    for label, reg, f in (("tAA (CL)", "TC_BANK_RANK_D", "tAA"), ("tCWL", "TC_BANK_RANK_D", "tCWL"),
                          ("tRCD", "TC_BANK", "tRCD"), ("tRP", "TC_BANK", "tRP"),
                          ("tRAS", "TC_BANK", "tRAS"), ("tRRD", "TC_BANK", "tRRD"),
                          ("tFAW", "TC_BANK_RANK_A", "tFAW"), ("tRDPRE", "TC_BANK", "tRDPRE"),
                          ("tWRPRE", "TC_BANK", "tWRPRE"), ("tCKE", "TC_BANK_RANK_A", "tCKE"),
                          ("tXP", "TC_BANK_RANK_C", "tXP"), ("tXPDLL", "TC_BANK_RANK_C", "tXPDLL"),
                          ("tREFI", "TC_RFTP", "tREFI"), ("tRFC", "TC_RFTP", "tRFC")):
        print(row(label, [g(ch, reg, f) for ch in chs]), file=out)
    print(header("Turnaround (sr/dr/dd)", chs), file=out)
    for label, reg in (("tRDRD", "TC_BANK_RANK_A"), ("tWRWR", "TC_BANK_RANK_B"),
                       ("tRDWR", "TC_BANK_RANK_C"), ("tWRRD", "TC_BANK_RANK_B")):
        print(row(label, ["%d/%d/%d" % tuple(g(ch, reg, "%s_%s" % (label, s))
                                              for s in ("sr", "dr", "dd")) for ch in chs]),
              file=out)
    print(header("ODT (ritardo/durata)", chs), file=out)
    print(row("lettura", ["%d/%d" % (g(ch, "TC_BANK_RANK_D", "odt_read_delay"),
                                     g(ch, "TC_BANK_RANK_D", "odt_read_duration")) for ch in chs]),
          file=out)
    print(row("scrittura", ["%d/%d" % (g(ch, "TC_BANK_RANK_D", "odt_write_delay"),
                                       g(ch, "TC_BANK_RANK_D", "odt_write_duration")) for ch in chs]),
          file=out)

    print("\nAndata e ritorno per rank: RTL (qclk) / IO latency", file=out)
    for ch in chs:
        cells = []
        for r in ranks_present(v, ch):
            rt = g(ch, "SC_ROUNDT_LAT", ("R0D0", "R1D0", "R0D1", "R1D1")[r])
            io = g(ch, "SC_IO_LATENCY", "iolat_rank%d" % r)
            cells.append("R%d %d/%d" % (r, rt, io))
        print("  C%d  %s   rt_iocomp %d" % (ch, "  ".join(cells), g(ch, "SC_IO_LATENCY", "rt_iocomp")),
              file=out)

    print("\nCLK/CTL per rank, CMD per gruppo (PI, 1/128 di clock)", file=out)
    for ch in chs:
        rp = ranks_present(v, ch)
        print("  C%d  CLK %s  CTL %s  CMD N %d/%d  CMD S %d/%d  CKE %d/%d" % (
            ch, "/".join(str(g(ch, "CLK_PI", "pi_%d" % r)) for r in rp),
            "/".join(str(g(ch, "CTL_PI", "pi_%d" % r)) for r in rp),
            g(ch, "CMD_N_PI", "pi_0"), g(ch, "CMD_N_PI", "pi_1"),
            g(ch, "CMD_S_PI", "pi_0"), g(ch, "CMD_S_PI", "pi_1"),
            g(ch, "CKE_CMD_PI", "pi_0"), g(ch, "CKE_CMD_PI", "pi_1")), file=out)

    print("\nAddestramento per byte (B0..B7)", file=out)
    for ch in chs:
        for r in ranks_present(v, ch):
            for label, reg, f in (("RcvEn", "RX_TRAIN", "rcven"), ("RxDqsP", "RX_TRAIN", "dqs_p"),
                                  ("RxDqsN", "RX_TRAIN", "dqs_n"), ("RxVref", "RX_TRAIN", "vref"),
                                  ("RxEq", "RX_TRAIN", "rx_eq"), ("TxDq", "TX_TRAIN", "dq_delay"),
                                  ("TxDqs", "TX_TRAIN", "dqs_delay"), ("TxEq", "TX_TRAIN", "tx_eq")):
                vals = [v["C%d.R%d.B%d %s.%s" % (ch, r, b, reg, f)] for b in range(BYTES)]
                print("  C%d.R%d %-7s %s" % (ch, r, label, " ".join("%4d" % x for x in vals)),
                      file=out)

    print("\nI/O per byte: offset di comp, ODT, sense amp (B0..B7)", file=out)
    for ch in chs:
        for label, reg, f in (("drv up", "DATA_OFFSET_COMP", "drv_up"),
                              ("drv down", "DATA_OFFSET_COMP", "drv_down"),
                              ("odt up", "DATA_OFFSET_COMP", "odt_up"),
                              ("odt down", "DATA_OFFSET_COMP", "odt_down"),
                              ("slew", "DATA_OFFSET_COMP", "slew_rate"),
                              ("tco", "DATA_OFFSET_COMP", "t_clk_out"),
                              ("odt delay", "DQ_CONTROL_1", "odt_delay"),
                              ("odt durata", "DQ_CONTROL_1", "odt_duration"),
                              ("samp delay", "DQ_CONTROL_1", "sense_amp_delay"),
                              ("samp durata", "DQ_CONTROL_1", "sense_amp_duration"),
                              ("rx bias", "DQ_CONTROL_1", "rx_bias_ctl"),
                              ("dqs ctle", "DQ_CONTROL_0", "rx_dqs_ctle"),
                              ("amp offset", "DQ_CONTROL_2", "rx_dqs_amp_offset"),
                              ("tx eq off", "DQ_CONTROL_2", "tx_eq_dis")):
            vals = [v["C%d.B%d %s.%s" % (ch, b, reg, f)] for b in range(BYTES)]
            print("  C%d %-11s %s" % (ch, label, " ".join("%4d" % x for x in vals)), file=out)

    print("\nComp globale e Vref", file=out)
    for reg in ("DATA_COMP_0", "DATA_COMP_1", "CMD_COMP", "CTL_COMP", "CLK_COMP", "COMP_CTL_0",
                "COMP_CTL_1", "VREF_ADJUST"):
        fs = [(k.split(".", 1)[1], x) for k, x in v.items() if k.startswith(reg + ".")]
        print("  %-12s %s" % (reg, " ".join("%s=%d" % f for f in fs)), file=out)
    print("  potenza      PM_PDWN_CONFIG=0x%x PM_SREF_CONFIG=0x%x PTM_CTL=0x%x" % (
        v["PM_PDWN_CONFIG"], v["PM_SREF_CONFIG"], v["PCU_DDR_PTM_CTL"]), file=out)


def split_byte(key):
    """("C0.R1", 3, "RX_TRAIN.rcven") per un campo di un byte, se no None."""
    first, _, rest = key.partition(" ")
    parts = first.split(".")
    if len(parts) > 1 and parts[-1][:1] == "B" and parts[-1][1:].isdigit():
        return ".".join(parts[:-1]), int(parts[-1][1:]), rest
    return None


def show(key, x):
    # i registri senza union (nessun campo dopo il nome) in esadecimale
    if key.endswith(".cmd_stretch"):
        return CMD_RATE.get(x, "%d" % x)
    return "0x%x" % x if "." not in key.split(" ")[-1] else "%d" % x


def compare(a, b, out):
    """I campi decodificati diversi tra due dump: quelli di un byte raccolti per
    canale, rank e campo, con i valori di B0..B7 di A e di B uno sotto l'altro."""
    (ia, ra), (ib, rb) = a, b
    va, vb = values(ra), values(rb)
    print("A: %s\nB: %s" % (ia.get("firmware", "?"), ib.get("firmware", "?")), file=out)
    diff = [k for k in va if k in vb and va[k] != vb[k]]
    groups, seen = [], set()
    for k in diff:
        sb = split_byte(k)
        if sb is None:
            groups.append(k)
        elif (sb[0], sb[2]) not in seen:
            seen.add((sb[0], sb[2]))
            groups.append((sb[0], sb[2]))
    print("\n%d campi diversi" % len(diff), file=out)
    for g in groups:
        if isinstance(g, str):
            print("  %-44s %12s -> %s" % (g, show(g, va[g]), show(g, vb[g])), file=out)
            continue
        prefix, rest = g
        key = lambda b: "%s.B%d %s" % (prefix, b, rest)
        for tag, vals in (("A", va), ("B", vb)):
            cells = [show(key(b), vals[key(b)]) if key(b) in vals else "-" for b in range(BYTES)]
            print("  %-34s %s %s" % ("%s %s" % (prefix, rest) if tag == "A" else "", tag,
                                       " ".join("%6s" % c for c in cells)), file=out)
    # la chiave dello scrambler cambia a ogni avvio a freddo (RDRAND)
    raw = [o for o in sorted(ra) if o in rb and ra[o] != rb[o] and o not in (0x2000, 0x2004)]
    print("\n%d registri a 32 bit diversi nel dump grezzo, chiave dello scrambler esclusa"
          % len(raw), file=out)


def main():
    ap = argparse.ArgumentParser(description="Il controller della memoria Haswell, dai registri")
    ap.add_argument("--save", help="scrive anche il dump dei registri in questo file")
    ap.add_argument("--file", help="il rapporto da un dump di --save, al posto dei registri")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"), help="i campi diversi tra due dump")
    args = ap.parse_args()
    if args.compare:
        compare(load(args.compare[0]), load(args.compare[1]), sys.stdout)
        return 0
    if args.file:
        info, regs = load(args.file)
    else:
        if os.geteuid() != 0:
            raise SystemExit("serve root (sudo) per leggere l'MCHBAR da /dev/mem")
        base, regs = read_mchbar()
        info = {"firmware": read_text("/sys/class/dmi/id/bios_version"), "mchbar": "0x%x" % base}
        if args.save:
            save(args.save, base, regs)
            print("dump: %s\n" % args.save)
    report(values(regs), info, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())

create_clock -name sys_clk -period 20.000 [get_ports {sys_clk}]
set_output_delay -max 5.000 -clock sys_clk [get_ports {HP_BCK HP_WS HP_DIN PA_EN i2s_bclk i2s_lrclk i2s_data debug_sample uart_tx key_addr[*] key_cs_n key_wr_n}]
set_output_delay -min 0.000 -clock sys_clk [get_ports {HP_BCK HP_WS HP_DIN PA_EN i2s_bclk i2s_lrclk i2s_data debug_sample uart_tx key_addr[*] key_cs_n key_wr_n}]
// Asynchronous UART enters only the first synchronizer FF.
set_false_path -from [get_ports {uart_rx}] -to [get_cells {controller/receiver/rx_meta*}]

create_generated_clock -name serial_clk -source [get_ports {sys_clk}] -divide_by 10 -multiply_by 49 [get_pins {pll/PLLA_inst/CLKOUT0}]
create_generated_clock -name pixel_clk -source [get_ports {sys_clk}] -divide_by 50 -multiply_by 49 [get_pins {pll/PLLA_inst/CLKOUT1}]
set_clock_groups -asynchronous -group [get_clocks {sys_clk}] -group [get_clocks {pixel_clk serial_clk}]
set_false_path -from [get_ports {key0_n key1_n}] -to [get_cells {buttons/next_sync* buttons/apply_sync*}]

create_generated_clock -name usb_clk -source [get_ports {sys_clk}] -divide_by 5 -multiply_by 6 [get_pins {native_usb/usb_pll/PLLA_inst/CLKOUT0}]
set_clock_groups -asynchronous -group [get_clocks {usb_clk}] -group [get_clocks {sys_clk pixel_clk serial_clk}]

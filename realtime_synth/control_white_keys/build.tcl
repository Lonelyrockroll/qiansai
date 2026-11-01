cd [file dirname [info script]]
exec C:/Users/ASUS/AppData/Local/Programs/Python/Python312/python.exe -X utf8 check_sources.py
open_project synth_display.gprj
set_option -top_module synth_display_top
set_option -output_base_name synth_display
set_option -place_option 1
set_option -use_cpu_as_gpio 1
run all

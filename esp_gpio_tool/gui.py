# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import sys

try:
    import tkinter as tk
    from tkinter import messagebox
    from tkinter import PhotoImage
    from tkinter import ttk
except ImportError as exc:
    raise SystemExit('Please install Python Tkinter, for more information see the documentation.') from exc

from esp_gpio_tool_cli.checker import run_check
from esp_gpio_tool_cli.chip import ESP
from esp_gpio_tool_cli.chip import SUPPORTED_CHIPS

# On different platforms tkinter.Event.delta is resolved differently
# The event.delta is used for scrolling (<MouseWheel>) event
# This constant ensures expected behavior of scrolling on all platforms
if sys.platform == 'darwin':
    PLF_SCROLL = 1
else:  # on Windows and Linux event.delta is multiple of 120
    PLF_SCROLL = 1 / 120


class GUI:
    """
    Simple GUI for the checker tool

    basic terminology for used variables:
    - peripheral     -> whole peripheral (such as ADC, I2C, ...)
    - sub_peripheral -> if more peripherals is used (such as ADC1, ADC2, ...)
    - pins           -> pins of peripherals (such as ADC1_CH0, ADC1_CH1, ...)
    """

    def __init__(self) -> None:
        def resource_path(relative_path: str) -> str:
            """Resource PATH extended with relative path as an argument"""
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'resources'))
            return os.path.join(base_path, relative_path)

        gui = tk.Tk()

        gui_width = int(gui.winfo_screenwidth() / 2)
        gui_height = int(gui.winfo_screenheight() / 2)
        gui_pos_x = int(gui_width / 2)
        gui_pos_y = int(gui_height / 5)
        gui_min_width = 600
        gui_min_height = 800

        gui.geometry(f'{gui_width}x{gui_height}+{gui_pos_x}+{gui_pos_y}')
        gui.title('ESP GPIO Tool')
        gui.minsize(width=gui_min_width, height=gui_min_height)
        gui.tk.call('wm', 'iconphoto', gui, PhotoImage(file=resource_path('espressif-logo.png')))

        header_frm = tk.Frame(master=gui, padx=10, pady=5)

        restore_btn = tk.Button(master=header_frm, text='Restore default')
        restore_btn.pack(side=tk.LEFT, anchor=tk.W)

        def restore_default(_: tk.Event) -> None:
            top = tk.Toplevel()

            restore_lbl = tk.Label(master=top, text='Do you really want to restore default state of GUI?', height=2)
            restore_lbl.pack(side=tk.TOP, padx=10)

            yes_btn = tk.Button(master=top, text='YES')
            yes_btn.pack(side=tk.LEFT, padx=50, pady=5)

            no_btn = tk.Button(master=top, text='NO')
            no_btn.pack(side=tk.RIGHT, padx=50, pady=5)

            def destroy_window(_: tk.Event) -> None:
                top.destroy()

            def yes_btn_callback(event: tk.Event) -> None:
                destroy_window(event)
                chip_selection_changed(event)

            no_btn.bind('<Button-1>', destroy_window)
            yes_btn.bind('<Button-1>', yes_btn_callback)

            top_width = restore_lbl.winfo_reqwidth()
            top_height = restore_lbl.winfo_reqheight() + yes_btn.winfo_reqheight() + 50

            top.title('Restore default')
            top.resizable(False, False)
            top.geometry(f'+{int(gui_width-top_width/2)}+{int(gui_height-top_height/2)}')
            top.tk.call('wm', 'iconphoto', top, PhotoImage(file=resource_path('espressif-logo.png')))

            top.mainloop()

        restore_btn.bind('<Button-1>', restore_default)

        chips_cmb = ttk.Combobox(
            master=header_frm,
            state='readonly',
            justify='center',
            values=SUPPORTED_CHIPS,
        )
        chips_cmb.current(0)
        chips_cmb.pack(side=tk.LEFT, anchor=tk.CENTER, expand=True)

        check_btn = tk.Button(master=header_frm, text='Check GPIOs')
        check_btn.pack(side=tk.RIGHT, anchor=tk.E)

        header_frm.pack(side=tk.TOP, fill=tk.BOTH)

        def on_button(_: tk.Event) -> None:
            """GPIO check button event handler
            - prepares user defined GPIOs for checker input and runs checker
            """
            user_gpios: dict[str, str] = {'chip': chips_cmb.get()}
            for pin, value in pins_values.items():
                gpio = value.get()
                if gpio == '-':
                    continue

                user_gpios[gpio.split('GPIO')[1].split(' ')[0]] = pin
            check = '\n '.join(run_check(user_input=user_gpios))
            if 'error' in check.lower():
                messagebox.showerror('Check - Error', check)
            elif 'warning' in check.lower():
                messagebox.showwarning('Check - Warning', check)
            else:
                messagebox.showinfo('Check', check)

        check_btn.bind('<Button-1>', on_button)

        pins_values: dict[str, ttk.Combobox] = {}
        self.gpios: list[str] = []

        def gpio_sel_changed(_: tk.Event) -> None:
            """GPIO from combobox selected event
            - removes already used GPIO from the combobox options for other pins
            """
            new_gpios: list[str] = self.gpios.copy()
            for value in pins_values.values():
                gpio = value.get()
                if gpio == '-':
                    continue

                if gpio in new_gpios:
                    new_gpios.remove(gpio)

            for __, value in pins_values.items():
                value.config(values=new_gpios)

        def mode_changed(event: tk.Event, peripheral: BasePeripheral, sub_peripheral: str) -> None:
            """Mode change event handler
            - sets the peripheral mode
            - disables/enables GPIO for specific mode
            """
            mode = event.widget.get().split(': ')
            mode = mode[1] if len(mode) == 2 else mode[0]

            peripheral.set_mode(sub_peripheral, mode)

            for pin in peripheral.all_pins[sub_peripheral]:
                if pin in peripheral.filtered_pins[sub_peripheral]:
                    pins_values[pin].configure(state='readonly')
                else:
                    pins_values[pin].configure(state='disabled')
                    pins_values[pin].current(0)

        container = tk.Frame(master=gui, width=100, bg='blue')

        canvas = tk.Canvas(master=container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
        scrollable_frm = ttk.Frame(canvas)
        scrollable_frm.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))

        def chip_selection_changed(event: (tk.Event | None)) -> None:
            """Target selected from chips Combobox event handler
            - draws all the peripherals, sub-peripherals and pins with a Combobox to fill the GPIOs
            """
            target = ESP(chips_cmb.get())
            self.gpios = []
            for gpio_num, gpio in target.gpios.items():
                self.gpios.append(f'GPIO{gpio_num} - {gpio.power_domain}')
            self.gpios.insert(0, '-')  # add a char for not used GPIO

            # clearing GUI and dictionary for GPIOs
            if event:
                canvas.delete('all')
                for widget in scrollable_frm.winfo_children():
                    widget.destroy()
                pins_values.clear()

            canvas.create_window((0, 0), window=scrollable_frm, anchor='nw')
            canvas.configure(yscrollcommand=scrollbar.set)

            color_switch = 2
            colors = ['#DCDCDC', 'white']

            for peripheral in target.peripherals:
                if peripheral.name == 'BasePeripheral':
                    continue

                row_frm = tk.Frame(
                    master=scrollable_frm,
                    width=200,
                    bg=colors[color_switch % 2],
                )
                column_left_frm = tk.Frame(
                    master=row_frm,
                    width=row_frm.winfo_width() / 3,
                )

                column_mid_frm = tk.Frame(
                    master=row_frm,
                    width=(row_frm.winfo_width() / 3) * 2,
                )

                row_sub_periph_frm = tk.Frame(
                    master=column_mid_frm,
                    width=column_mid_frm.winfo_width(),
                )

                column_sub_periph_mid_frm = tk.Frame(
                    master=row_sub_periph_frm, width=row_sub_periph_frm.winfo_width() / 2, bg=row_frm['bg']
                )

                column_sub_periph_right_frm = tk.Frame(
                    master=row_sub_periph_frm,
                    width=row_sub_periph_frm.winfo_width() / 2,
                )

                peripheral_lbl = tk.Label(
                    master=column_left_frm, text=peripheral.name, width=15, bg=row_frm['bg'], fg='black'
                )
                peripheral_lbl.pack(side=tk.LEFT, anchor=tk.NW, fill=tk.BOTH)
                peripheral_lbl.bind('<MouseWheel>', on_mousewheel)
                if sys.platform == 'linux':
                    peripheral_lbl.bind('<Button-4>', on_mousewheel_linux_down)
                    peripheral_lbl.bind('<Button-5>', on_mousewheel_linux_up)

                for sub_periph in peripheral.all_pins.keys():
                    sub_periph_lbl = tk.Label(
                        master=column_sub_periph_mid_frm,
                        text=sub_periph,
                        width=5,
                        height=len(peripheral.all_pins[sub_periph]),
                        bg=row_frm['bg'],
                        fg='black',
                    )
                    sub_periph_lbl.pack(side=tk.TOP, anchor=tk.CENTER, fill=tk.BOTH, expand=True)
                    sub_periph_lbl.bind('<MouseWheel>', on_mousewheel)
                    if sys.platform == 'linux':
                        sub_periph_lbl.bind('<Button-4>', on_mousewheel_linux_down)
                        sub_periph_lbl.bind('<Button-5>', on_mousewheel_linux_up)
<<<<<<< HEAD
=======
                    # peripheral mode select
                    if peripheral.supported_modes:
                        sub_periph_modes: list[str] = []
                        for mode in peripheral.supported_modes[sub_periph]:
                            if peripheral.mode_label is None:
                                sub_periph_modes.append(str(mode))
                            else:
                                sub_periph_modes.append(f'{peripheral.mode_label}: {str(mode)}')

                        sub_periph_mode_cmb = ttk.Combobox(
                            master=column_sub_periph_mid_frm,
                            state='readonly',
                            justify='center',
                            values=sub_periph_modes,
                            width=25,
                        )
                        sub_periph_mode_cmb.pack(side=tk.TOP, anchor=tk.S, expand=True)
                        sub_periph_mode_cmb.current(
                            peripheral.supported_modes[sub_periph].index(peripheral.mode[sub_periph])
                        )
                        sub_periph_mode_cmb.bind(
                            '<<ComboboxSelected>>',
                            lambda event, periph=peripheral, sub_periph=sub_periph: mode_changed(  # type: ignore[misc]
                                event, periph, sub_periph
                            ),
                        )

                    line_sub_cns = tk.Canvas(master=column_sub_periph_mid_frm, height=1, width=200, background='grey')
                    line_sub_cns.pack(side=tk.TOP)
                    line_sub_cns.bind('<MouseWheel>', on_mousewheel)
                    if sys.platform == 'linux':
                        line_sub_cns.bind('<Button-4>', on_mousewheel_linux_down)
                        line_sub_cns.bind('<Button-5>', on_mousewheel_linux_up)
>>>>>>> 97424d8 (fix(gui): Fixed spaces between lines)

                pin_row = 0
                for pins in peripheral.all_pins.values():
                    for pin in pins:
                        pin_lbl = tk.Label(
                            master=column_sub_periph_right_frm, text=pin, width=30, bg=row_frm['bg'], fg='black'
                        )
                        pin_lbl.grid(row=pin_row, column=0, sticky='nsew')
                        pin_lbl.bind('<MouseWheel>', on_mousewheel)
                        if sys.platform == 'linux':
                            pin_lbl.bind('<Button-4>', on_mousewheel_linux_down)
                            pin_lbl.bind('<Button-5>', on_mousewheel_linux_up)

                        pins_values[pin] = ttk.Combobox(
                            master=column_sub_periph_right_frm, state='readonly', values=self.gpios, justify='center'
                        )
                        pins_values[pin].current(0)
                        pins_values[pin].grid(row=pin_row, column=1, sticky='nsew')
                        pins_values[pin].bind('<<ComboboxSelected>>', gpio_sel_changed)

                        pin_row += 1

                    line_cns = tk.Canvas(master=column_sub_periph_right_frm, height=1, background='grey')
                    line_cns.grid(row=pin_row, column=0, columnspan=2, sticky='nsew')
                    line_cns.bind('<MouseWheel>', on_mousewheel)
                    if sys.platform == 'linux':
                        line_cns.bind('<Button-4>', on_mousewheel_linux_down)
                        line_cns.bind('<Button-5>', on_mousewheel_linux_up)

                    pin_row += 1

                column_left_frm.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                column_mid_frm.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                column_sub_periph_mid_frm.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                column_sub_periph_right_frm.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                row_sub_periph_frm.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                row_frm.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
                color_switch += 1

            container.pack(fill=tk.BOTH, side=tk.LEFT, expand=True)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def on_mousewheel(event: tk.Event) -> None:
            """Mousewheel event handler"""
            canvas.yview_scroll(int(-1 * (event.delta * PLF_SCROLL)), 'units')

        def on_mousewheel_linux_up(_: tk.Event) -> None:
            """Mousewheel event handler for linux - up scroll"""
            canvas.yview_scroll(1, 'units')

        def on_mousewheel_linux_down(_: tk.Event) -> None:
            """Mousewheel event handler for linux - down scroll"""
            canvas.yview_scroll(-1, 'units')

        canvas.bind('<MouseWheel>', on_mousewheel)
        if sys.platform == 'linux':
            canvas.bind('<Button-4>', on_mousewheel_linux_down)
            canvas.bind('<Button-5>', on_mousewheel_linux_up)
        chips_cmb.bind('<<ComboboxSelected>>', chip_selection_changed)

        chip_selection_changed(event=None)

        gui.mainloop()

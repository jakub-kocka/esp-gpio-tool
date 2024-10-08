# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import itertools
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
from esp_gpio_tool_cli.peripheral import BasePeripheral

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
            base_path = os.path.abspath(os.path.dirname(__file__))
            return os.path.join(base_path, 'resources', relative_path)

        gui = tk.Tk()

        gui_min_width = 925
        gui_min_height = 600
        gui_width = int(gui.winfo_screenwidth() / 2)
        gui_height = int(gui.winfo_screenheight() / 2)
        gui_pos_x = int(gui_width - gui_min_width / 2)
        gui_pos_y = int(gui_height / 5)

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
        chips_cmb.pack(side=tk.LEFT, anchor=tk.E, expand=True)

        variants_cmb = ttk.Combobox(
            master=header_frm,
            state='readonly',
            justify='center',
            values=['-'] + [str(soc) for soc in ESP(chips_cmb.get()).soc_list],
        )
        variants_cmb.pack(side=tk.LEFT, anchor=tk.W, expand=True)

        check_btn = tk.Button(master=header_frm, text='Check GPIOs')
        check_btn.pack(side=tk.RIGHT, anchor=tk.E)

        header_frm.pack(side=tk.TOP, fill=tk.BOTH)

        def on_button(_: tk.Event) -> None:
            """GPIO check button event handler
            - prepares user defined GPIOs for checker input and runs checker
            """
            user_gpios: dict[str, str | list] = {'chip': chips_cmb.get()}
            variant = variants_cmb.get()
            if variant not in ['-', 'Optional SoC variant']:
                user_gpios['soc'] = variant
            for pin, value in pins_values.items():
                gpio = value.get()
                if gpio == '-':
                    continue
                key = gpio.split('GPIO')[1].split(' ')[0]

                if key in user_gpios:
                    if isinstance(user_gpios[key], list):
                        user_gpios[key].append(pin)  # type: ignore
                    else:
                        user_gpios[key] = [user_gpios[key], pin]
                else:
                    user_gpios[key] = pin

            check = '\n '.join(run_check(user_input=user_gpios))
            if 'error' in check.lower():
                messagebox.showerror('Check - Error', check)
            elif 'warning' in check.lower():
                messagebox.showwarning('Check - Warning', check)
            else:
                messagebox.showinfo('Check', check)

        check_btn.bind('<Button-1>', on_button)

        pins_values: dict[str, ttk.Combobox] = {}
        self.target: ESP = ESP(chips_cmb.get())

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

        container = tk.Frame(master=gui)

        def on_canvas_configure(event: tk.Event) -> None:
            """Adjust the width of the scrollable frame based on the canvas width"""
            canvas_width = event.width
            canvas.itemconfig(self.canvas_window, width=canvas_width)
            scrollable_frm.config(width=canvas_width)
            canvas.configure(scrollregion=canvas.bbox('all'))

        def on_frame_configure(_: tk.Event) -> None:
            """Update the scroll region of the canvas based on the size of the scrollable frame"""
            canvas.configure(scrollregion=canvas.bbox('all'))

        def on_container_configure(_: tk.Event) -> None:
            """Adjust the visible region of the canvas when resizing the window"""
            canvas.configure(scrollregion=canvas.bbox('all'))
            canvas.yview_moveto(scrollbar.get()[0])

        canvas = tk.Canvas(master=container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
        scrollable_frm = ttk.Frame(canvas)
        scrollable_frm.bind('<Configure>', on_frame_configure)

        self.canvas_window = canvas.create_window((0, 0), window=scrollable_frm, anchor='nw')
        canvas.bind('<Configure>', on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        container.bind('<Configure>', on_container_configure)

        def chip_selection_changed(event: (tk.Event | None), variant: bool = False) -> None:
            """Target selected from chips Combobox event handler
            - draws all the peripherals, sub-peripherals and pins with a Combobox to fill the GPIOs
            """
            self.target = ESP(chips_cmb.get())
            if variant:
                if variants_cmb.get() != '-':
                    self.target.set_soc(variants_cmb.get())
            else:
                variants_cmb['values'] = ['-'] + self.target.soc_list
                variants_cmb.set('Optional SoC variant')

            # clearing GUI and dictionary for GPIOs
            if event:
                canvas.delete('all')
                for widget in scrollable_frm.winfo_children():
                    widget.destroy()
                pins_values.clear()
                self.canvas_window = canvas.create_window((0, 0), window=scrollable_frm, anchor='nw')
                canvas.itemconfig(self.canvas_window, width=scrollable_frm.winfo_width())

            color_switch = 2
            colors = ['#DCDCDC', 'white']

            for peripheral in self.target.peripherals:
                if peripheral.name == 'BasePeripheral':
                    continue

                row_frm = tk.Frame(
                    master=scrollable_frm,
                    bg=colors[color_switch % 2],
                )
                column_left_frm = tk.Frame(
                    master=row_frm,
                )

                column_mid_frm = tk.Frame(
                    master=row_frm,
                )

                row_sub_periph_frm = tk.Frame(
                    master=column_mid_frm,
                )

                column_sub_periph_mid_frm = tk.Frame(master=row_sub_periph_frm, bg=row_frm['bg'])
                column_sub_periph_mid_frm.bind('<MouseWheel>', on_mousewheel)
                if sys.platform == 'linux':
                    column_sub_periph_mid_frm.bind('<Button-4>', on_mousewheel_linux_down)
                    column_sub_periph_mid_frm.bind('<Button-5>', on_mousewheel_linux_up)

                column_sub_periph_right_frm = tk.Frame(
                    master=row_sub_periph_frm,
                )
                column_sub_periph_right_frm.bind('<MouseWheel>', on_mousewheel)
                if sys.platform == 'linux':
                    column_sub_periph_right_frm.bind('<Button-4>', on_mousewheel_linux_down)
                    column_sub_periph_right_frm.bind('<Button-5>', on_mousewheel_linux_up)

                peripheral_lbl = tk.Label(
                    master=column_left_frm, text=peripheral.name, width=15, bg=row_frm['bg'], fg='black'
                )
                peripheral_lbl.pack(side=tk.LEFT, anchor=tk.NW, fill=tk.BOTH, expand=True)
                peripheral_lbl.bind('<MouseWheel>', on_mousewheel)
                if sys.platform == 'linux':
                    peripheral_lbl.bind('<Button-4>', on_mousewheel_linux_down)
                    peripheral_lbl.bind('<Button-5>', on_mousewheel_linux_up)

                for sub_periph in peripheral.all_pins.keys():
                    sub_periph_lbl = tk.Label(
                        master=column_sub_periph_mid_frm,
                        text=sub_periph,
                        height=len(peripheral.all_pins[sub_periph]) - (1 if peripheral.supported_modes else 0),
                        bg=row_frm['bg'],
                        fg='black',
                    )
                    sub_periph_lbl.pack(side=tk.TOP, anchor=tk.CENTER, fill=tk.BOTH, expand=True)
                    sub_periph_lbl.bind('<MouseWheel>', on_mousewheel)
                    if sys.platform == 'linux':
                        sub_periph_lbl.bind('<Button-4>', on_mousewheel_linux_down)
                        sub_periph_lbl.bind('<Button-5>', on_mousewheel_linux_up)
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
                        )
                        sub_periph_mode_cmb.pack(side=tk.TOP, anchor=tk.S, expand=True, ipadx=5)
                        sub_periph_mode_cmb.current(
                            peripheral.supported_modes[sub_periph].index(peripheral.mode[sub_periph])
                        )
                        sub_periph_mode_cmb.bind(
                            '<<ComboboxSelected>>',
                            lambda event, periph=peripheral, sub_periph=sub_periph: mode_changed(  # type: ignore[misc]
                                event, periph, sub_periph
                            ),
                        )

                    line_sub_cns = tk.Canvas(master=column_sub_periph_mid_frm, height=1, background='grey')
                    line_sub_cns.pack(side=tk.TOP, anchor=tk.S, expand=True, fill=tk.X)
                    line_sub_cns.bind('<MouseWheel>', on_mousewheel)
                    if sys.platform == 'linux':
                        line_sub_cns.bind('<Button-4>', on_mousewheel_linux_down)
                        line_sub_cns.bind('<Button-5>', on_mousewheel_linux_up)

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

                        gpios = [str(pin) for pin in self.target.list_pins_by_function(pin)]
                        gpios.insert(0, '-')  # add a char for not used GPIO
                        pins_values[pin] = ttk.Combobox(
                            master=column_sub_periph_right_frm, state='readonly', values=gpios, justify='center'
                        )
                        pins_values[pin].current(0)
                        pins_values[pin].grid(row=pin_row, column=1, sticky='nsew')

                        if peripheral.supported_modes and pin not in list(
                            itertools.chain.from_iterable(peripheral.filtered_pins.values())
                        ):
                            pins_values[pin].configure(state='disabled')

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

            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            container.pack(fill=tk.BOTH, side=tk.LEFT, expand=True)

        def on_mousewheel(event: tk.Event) -> None:
            """Mousewheel event handler"""
            canvas.yview_scroll(int(-1 * (event.delta * PLF_SCROLL)), 'units')

        def on_mousewheel_linux_up(_: tk.Event) -> None:
            """Mousewheel event handler for linux - up scroll"""
            canvas.yview_scroll(1, 'units')

        def on_mousewheel_linux_down(_: tk.Event) -> None:
            """Mousewheel event handler for linux - down scroll"""
            canvas.yview_scroll(-1, 'units')

        container.bind('<MouseWheel>', on_mousewheel)
        if sys.platform == 'linux':
            container.bind('<Button-4>', on_mousewheel_linux_down)
            container.bind('<Button-5>', on_mousewheel_linux_up)

        canvas.bind('<MouseWheel>', on_mousewheel)
        if sys.platform == 'linux':
            canvas.bind('<Button-4>', on_mousewheel_linux_down)
            canvas.bind('<Button-5>', on_mousewheel_linux_up)

        chips_cmb.bind('<<ComboboxSelected>>', chip_selection_changed)
        variants_cmb.bind('<<ComboboxSelected>>', lambda event: chip_selection_changed(event, variant=True))
        gui.option_add('*TCombobox*Listbox.Justify', 'center')

        chip_selection_changed(event=None)

        gui.mainloop()

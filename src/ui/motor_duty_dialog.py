"""Tk 입력 어댑터. 물리 계산은 src.core.motor_dynamics에만 둔다."""
import tkinter as tk
from tkinter import ttk

from src.core.motor_dynamics import MotorDutyInput, estimate_motor_duty
from src.core.errors import CalculationInputError


FIELD_SPECS = (
    ('distance_m', '운행 거리 (m)', '30'), ('speed_m_s', '카 속도 (m/s)', '2'),
    ('accel_m_s2', '최대 가속도 (m/s²)', '1'), ('jerk_m_s3', '저크 (m/s³)', '.8'),
    ('car_kg', '카 질량 (kg)', '1000'), ('load_kg', '실제 적재 (kg)', '500'),
    ('rated_load_kg', '정격 적재 (kg)', '1000'),
    ('counterweight_kg', '균형추 질량 (kg)', '1500'),
    ('extra_mass_kg', '추가 등가 질량 (kg)', '300'),
    ('sheave_radius_m', '권상 도르래 반지름 (m)', '.4'),
    ('gear_ratio', '기어비 (모터축/도르래축)', '1'),
    ('roping_ratio', '로핑비 (로프속도/카속도)', '1'),
    ('motor_inertia_kg_m2', '모터축 합성 관성 J (kg·m²)', '2'),
    ('resistance_n', '운행 방향 저항력 (N)', '100'),
    ('efficiency', '구동 효율 (0~1)', '.85'),
    ('cycle_s', '운전 반복 주기 (s)', '120'),
    ('regen_fraction', '회생 분담 비율 (0~1)', '0'),
    ('step_s', '궤적 시간 간격 (s)', '.05'),
)


def open_motor_duty_dialog(panel):
    window = tk.Toplevel(panel)
    window.title('관성·가속 토크 및 운전주기 추정')
    window.geometry('760x760')
    window.minsize(650, 580)
    body = ttk.Frame(window, padding=12)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text='모터축 관성·열부하·제동저항기 추정 (제조사 정격 검토 필요)',
              font=('맑은 고딕', 12, 'bold')).pack(anchor='w', pady=(0, 6))
    outer = ttk.Frame(body)
    outer.pack(fill='both', expand=True)
    canvas = tk.Canvas(outer, highlightthickness=0)
    scroll = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side='left', fill='both', expand=True)
    scroll.pack(side='right', fill='y')
    form = ttk.Frame(canvas)
    canvas.create_window((0, 0), window=form, anchor='nw')
    form.bind('<Configure>', lambda _event: canvas.configure(scrollregion=canvas.bbox('all')))

    saved = getattr(panel, 'advanced_inputs', {})
    defaults = dict((key, default) for key, _, default in FIELD_SPECS)
    if not saved:
        try:
            defaults['load_kg'] = panel.entries['Q'].get().strip() or defaults['load_kg']
            velocity = float(panel.entries['V'].get())
            unit = panel.unit_vars['V'].get()
            defaults['speed_m_s'] = str(velocity if unit == 'm/s' else velocity / 60)
        except (ValueError, KeyError, AttributeError):
            pass
    entries = {}
    for row, (key, label, _default) in enumerate(FIELD_SPECS):
        ttk.Label(form, text=label, width=35).grid(row=row, column=0, sticky='w', pady=2)
        entry = ttk.Entry(form, width=17)
        entry.insert(0, saved.get(key, defaults[key]))
        entry.grid(row=row, column=1, sticky='w', pady=2)
        entries[key] = entry
    direction = tk.StringVar(value=saved.get('direction', '상승'))
    ttk.Label(form, text='운행 방향', width=35).grid(row=len(FIELD_SPECS), column=0, sticky='w')
    ttk.Combobox(form, textvariable=direction, values=('상승', '하강'),
                 state='readonly', width=14).grid(row=len(FIELD_SPECS), column=1, sticky='w')
    result = tk.Text(body, height=10, wrap='word')
    result.pack(fill='x', pady=6)
    result.insert('1.0', '실제 카·균형추·관성과 운전 주기를 입력하고 계산하세요.')
    result.configure(state='disabled')

    def show(message):
        result.configure(state='normal')
        result.delete('1.0', 'end')
        result.insert('1.0', message)
        result.configure(state='disabled')

    def calculate(_event=None):
        raw = {key: entry.get() for key, entry in entries.items()}
        raw['direction'] = direction.get()
        try:
            inputs = MotorDutyInput(**raw)
            data = estimate_motor_duty(inputs)
        except (CalculationInputError, TypeError) as exc:
            show(f'입력 확인: {exc}')
            return
        panel.advanced_inputs = raw
        show('\n'.join((
            f"주행 {data['run_time_s']:.3f} s / 반복 주기 {data['cycle_s']:.1f} s / 운전율 {data['duty_ed_pct']:.2f}% ED",
            f"모터축 환산 관성 {data['reflected_inertia_kg_m2']:.4f} kg·m² / 최대 축속도 {data['peak_motor_rad_s']:.3f} rad/s",
            f"최대 요구 축토크(절댓값) {data['peak_torque_nm']:.3f} N·m / 최고 구동 입력 {data['peak_input_kw']:.3f} kW",
            f"모터 열 추정용 반복주기 RMS 토크 {data['thermal_rms_torque_nm']:.3f} N·m",
            f"저항기 최고 {data['resistor_peak_kw']:.3f} kW / 회당 {data['resistor_cycle_kj']:.3f} kJ / 반복주기 평균 {data['resistor_average_kw']:.3f} kW",
            '※ 모터 허용 피크·연속 토크 및 저항기 피크·평균·펄스 정격은 제조사 자료와 비교하세요.',
            '※ 회생 비율은 브레이크 에너지의 분담 가정이며 마찰식 안전제동기 온도는 계산하지 않습니다.',
        )))

    ttk.Button(body, text='관성·열부하 계산', command=calculate).pack(anchor='w')
    for entry in entries.values():
        entry.bind('<Return>', calculate)
    window.transient(panel.winfo_toplevel())
    entries['distance_m'].focus_set()
    return window

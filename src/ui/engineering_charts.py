"""간이 로프 장력과 5분 층별 수송 결과의 작은 Tk 차트."""
import tkinter as tk
from tkinter import messagebox

from src.core.capacity import simulate_five_minutes
from src.core.rope_traction import tension_by_height
from src.core.errors import CalculationInputError


def _chart_window(parent, title, subtitle):
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.geometry('780x500')
    tk.Label(dialog, text=subtitle, anchor='w', wraplength=740,
             font=('맑은 고딕', 10)).pack(fill='x', padx=15, pady=8)
    chart = tk.Canvas(dialog, bg='white', height=390, highlightthickness=0)
    chart.pack(fill='both', expand=True, padx=15, pady=5)
    return dialog, chart


def show_tension(panel):
    try:
        values = [float(panel.entries[key].get().replace(',','')) for key in
                  ('Wc','Q','OB','H','wr','n')]
        samples = tension_by_height(values[0], values[1], values[2]/100,
                                    values[3], values[4], values[5])
    except (CalculationInputError,ValueError,OverflowError) as error:
        messagebox.showerror('장력 입력 확인', str(error), parent=panel)
        return
    dialog, canvas = _chart_window(panel, '로프 가닥별 정적 장력 분포',
        '입력한 카 자중·하중·균형추 비율·로프 중량만 적용한 위치별 모델 (가속·보상체인 제외)')

    def redraw(_event=None):
        canvas.delete('all')
        w, h = max(500,canvas.winfo_width()), max(250,canvas.winfo_height())
        x0,x1,y0,y1=85,w-30,35,h-55
        maximum=max(max(a,b) for _,a,b in samples)*1.1
        for index in range(6):
            y=y1-(y1-y0)*index/5
            canvas.create_line(x0,y,x1,y,fill='#e2e8ed')
            canvas.create_text(x0-8,y,text=f'{maximum*index/5:.0f}',anchor='e')
        for index in range(6):
            x=x0+(x1-x0)*index/5
            canvas.create_line(x,y0,x,y1,fill='#e2e8ed')
            canvas.create_text(x,y1+16,text=f'{samples[-1][0]*index/5:.1f}')
        for col,color in ((1,'#2879cc'),(2,'#d37a28')):
            points=[]
            for row in samples:
                distance,value=row[0],row[col]
                points += [x0+(x1-x0)*distance/samples[-1][0],y1-(y1-y0)*value/maximum]
            canvas.create_line(*points,fill=color,width=2)
        canvas.create_text(x0,y0-22,text='파랑: 카측 / 주황: 균형추측  ·  N/가닥',anchor='w')
        canvas.create_text(x1,y1+34,text='카의 최하층부터 위치 (m)',anchor='e')
    canvas.bind('<Configure>',redraw)
    return dialog


def show_capacity(panel):
    data = getattr(panel,'last_capacity_inputs',None)
    if not data:
        messagebox.showinfo('교통량 분석', '교통량을 먼저 계산하세요.', parent=panel)
        return
    try:
        result = simulate_five_minutes(**data)
    except CalculationInputError as error:
        messagebox.showerror('수송 시뮬레이션', str(error), parent=panel)
        return
    dialog, canvas = _chart_window(panel, '층별 5분 수송 인원',
        f"완료된 5분 운행: {result['completed_people']}명 / 가상 균등 목적층·고정 탑승률 (seed=42). "
        '실제 대기열 및 배차 알고리즘을 반영하지 않습니다.')
    values=result['per_floor']

    def redraw(_event=None):
        canvas.delete('all')
        w,h=max(500,canvas.winfo_width()),max(250,canvas.winfo_height())
        x0,x1,y0,y1=60,w-25,25,h-55
        maximum=max(1,max(values))
        for tick in range(6):
            y=y1-(y1-y0)*tick/5
            canvas.create_line(x0,y,x1,y,fill='#e2e8ed')
            canvas.create_text(x0-8,y,text=f'{maximum*tick/5:.0f}',anchor='e')
        bar=(x1-x0)/len(values)
        for idx,count in enumerate(values):
            x=x0+idx*bar
            canvas.create_rectangle(x+1,y1-(y1-y0)*count/maximum,x+max(2,bar-1),y1,
                                    fill='#2879cc',outline='')
            if idx==0 or (idx+1)%max(1,len(values)//10)==0:
                canvas.create_text(x+bar/2,y1+13,text=str(idx+2),font=('맑은 고딕',8))
        canvas.create_text(x0,y0-13,text='층별 완료 탑승 인원 (명)',anchor='w')
        canvas.create_text(x1,y1+34,text='목적층',anchor='e')
    canvas.bind('<Configure>',redraw)
    return dialog

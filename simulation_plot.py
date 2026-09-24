"""Tk Canvas에서 시간별 속도와 부호가 있는 기계동력을 표시한다."""


def draw_scurve_plot(canvas, profile, palette):
    canvas.delete('all')
    if not profile:
        return
    width = max(320, canvas.winfo_width())
    height = max(200, canvas.winfo_height())
    ink = palette['text']
    grid = palette['border']
    speed_color = palette['accent']
    power_color = '#e39738' if palette['background'] == '#000000' else '#a35000'
    background = palette['surface']
    canvas.configure(bg=background)
    left, right = 73, width - 16
    if right <= left:
        return
    points = profile['samples']
    electrical = 'grid_kw_samples' in profile
    powers = profile['grid_kw_samples'] if electrical else profile['signed_mechanical_kw_samples']
    duration = max(profile['duration_s'], 1e-12)
    upper = (25, max(85, height*0.45 - 12))
    lower = (height*0.55, height - 32)

    def trace(label, values, bounds, top, bottom, color):
        low, high = bounds
        high = max(low + 1e-9, high)
        canvas.create_text(left, top-11, text=label, anchor='w', fill=ink,
                           font=('맑은 고딕', 9, 'bold'))
        canvas.create_line(left, top, left, bottom, right, bottom, fill=grid)
        if low < 0 < high:
            zero = bottom - (0-low)/(high-low)*(bottom-top)
            canvas.create_line(left,zero,right,zero,fill=grid,dash=(3,3))
        for label_value in (low, high):
            y = bottom-(label_value-low)/(high-low)*(bottom-top)
            canvas.create_text(left-6,y,text=f'{label_value:.1f}',anchor='e',fill=ink,
                               font=('맑은 고딕',8))
        stride = max(1, len(points)//400)
        indices = list(range(0,len(points),stride))
        if indices[-1] != len(points)-1:
            indices.append(len(points)-1)
        coordinates=[]
        for index in indices:
            x = left + points[index][0]/duration*(right-left)
            y = bottom-(values[index]-low)/(high-low)*(bottom-top)
            coordinates.extend((x,y))
        if len(coordinates)>=4:
            canvas.create_line(*coordinates,fill=color,width=2,smooth=False)

    speed = [point[2] for point in points]
    trace('속도 (m/s)',speed,(0.,max(speed)*1.05),*upper,speed_color)
    lower_limit = min(0.,min(powers))
    upper_limit = max(0.,max(powers))
    if lower_limit == upper_limit:
        upper_limit=1.
    trace('추정 계통전력 (kW, +소비 / −회수)' if electrical else '예상 기계동력 (kW, +구동 / −제동)',powers,
          (lower_limit*1.05,upper_limit*1.05),*lower,power_color)
    canvas.create_text((left+right)/2,height-7,text=f'시간 (s)  0 → {duration:.2f}',
                       fill=ink,font=('맑은 고딕',8))


def draw_energy_comparison(canvas, reference, candidate, palette):
    """동일 가로 시간축에 기준과 후보의 속도·추정 계통전력을 겹쳐 그린다."""
    canvas.delete('all')
    if not reference or not candidate:return
    width=max(320,canvas.winfo_width());height=max(175,canvas.winfo_height())
    canvas.configure(bg=palette['surface'])
    left,right=72,width-18
    duration=max(reference['duration_s'],candidate['duration_s'])
    ink=palette['text'];grid=palette['border']
    colors=('#2879cc','#d37a28') if palette['background']!='#000000' else ('#76adff','#ffbb77')
    canvas.create_text(left,12,text='기준(파랑) / 후보(주황)',anchor='w',fill=ink,font=('맑은 고딕',9,'bold'))
    for key,label,top,bottom in (('speed','속도 m/s',32,75),('power','계통전력 kW (+소비 / −회수)',97,height-24)):
        series=[]
        for profile in (reference,candidate):
            values=([sample[2] for sample in profile['samples']] if key=='speed' else profile['grid_kw_samples'])
            series.append(values)
        minimum=min(0.,*(min(v) for v in series));maximum=max(0.,*(max(v) for v in series))
        if maximum-minimum<1e-12:maximum=minimum+1
        canvas.create_text(left,top-9,text=label,anchor='w',fill=ink,font=('맑은 고딕',8))
        zero=bottom-(0-minimum)/(maximum-minimum)*(bottom-top)
        canvas.create_line(left,zero,right,zero,fill=grid,dash=(3,3))
        for profile,values,color in zip((reference,candidate),series,colors):
            stride=max(1,len(values)//350)
            indices=list(range(0,len(values),stride))
            if indices[-1]!=len(values)-1:indices.append(len(values)-1)
            coords=[]
            for i in indices:
                coords.extend((left+profile['samples'][i][0]/duration*(right-left),
                               bottom-(values[i]-minimum)/(maximum-minimum)*(bottom-top)))
            if len(coords)>=4:canvas.create_line(*coords,fill=color,width=2)
        canvas.create_text(left-5,top,text=f'{maximum:.1f}',anchor='e',fill=ink,font=('맑은 고딕',8))
        canvas.create_text(left-5,bottom,text=f'{minimum:.1f}',anchor='e',fill=ink,font=('맑은 고딕',8))
    canvas.create_text(right,height-8,text=f'시간 0~{duration:.2f} s',anchor='e',fill=ink,font=('맑은 고딕',8))

# Pillow 렌더러는 화면과 PNG 저장에 같은 눈금과 데이터 샘플을 사용한다.
_legacy_draw_scurve_plot=draw_scurve_plot
_legacy_draw_energy_comparison=draw_energy_comparison

def draw_scurve_plot(canvas,profile,palette):
    if not hasattr(canvas,'tk'):
        return _legacy_draw_scurve_plot(canvas,profile,palette)
    try:
        from plot_render import draw_on_canvas
        return draw_on_canvas(canvas,profile,palette)
    except ImportError:
        return _native_draw(canvas,profile,palette)

def draw_energy_comparison(canvas,reference,candidate,palette):
    if not hasattr(canvas,'tk'):
        return _legacy_draw_energy_comparison(canvas,reference,candidate,palette)
    try:
        from plot_render import draw_on_canvas
        return draw_on_canvas(canvas,candidate,palette,reference)
    except ImportError:
        return _native_draw(canvas,candidate,palette,reference)


def _native_draw(canvas,profile,palette,reference=None):
    """외부 패키지가 없는 실행 파일에서도 중간 눈금과 보조선을 그린다."""
    import base64
    from tkinter import PhotoImage, TclError
    from native_plot import render_png
    canvas.delete('all')
    if not profile:return
    width=max(360,min(1800,canvas.winfo_width()-4))
    height=max(200,min(750,canvas.winfo_height()-4))
    try:
        encoded=base64.b64encode(render_png(profile,palette,reference,(width,height))).decode('ascii')
        photo=PhotoImage(master=canvas,data=encoded,format='png')
    except TclError:
        if reference:return _legacy_draw_energy_comparison(canvas,reference,profile,palette)
        return _legacy_draw_scurve_plot(canvas,profile,palette)
    canvas._plot_photo=photo
    canvas.create_image(canvas.winfo_width()/2,canvas.winfo_height()/2,image=photo)

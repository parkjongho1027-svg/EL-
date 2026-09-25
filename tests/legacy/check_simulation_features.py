"""기록 내구성과 동일 렌더러의 그래프·PNG 크기 확인."""
import tempfile
from pathlib import Path
from src.persistence import storage
from src.ui.plot_render import render_plot
from src.core.elevator_review_engine import scurve_profile

with tempfile.TemporaryDirectory() as tmp:
    original=storage.get_data_file_path
    storage.get_data_file_path=lambda:Path(tmp)/'user_data.json'
    try:
        store=storage.PersistentStore()
        state={'distance':'30','_energy':{'ref_vmax':'2'}}
        store.add_simulation('mechanical',state,'18초')
        store.add_simulation('electrical',state,'0.003 kWh')
        again=storage.PersistentStore()
        assert len(again.simulation_history())==2
        assert len(again.simulation_history('mechanical'))==1
        assert again.simulation_history('electrical')[0][1]['__state__']==state
        again.delete_simulation(0)
        assert len(storage.PersistentStore().simulation_history())==1
    finally:
        storage.get_data_file_path=original
p=scurve_profile(30,2,1,0.8,1500)
palette={'surface':'#f7faff','text':'#222222','background':'#ffffff','accent':'#2879cc'}
image=render_plot(p,palette,size=(820,255),scale=2)
assert image.size==(1640,510)
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/'plot.png';image.save(path)
    assert path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
print('시뮬레이션 기록 영구 저장·삭제, PNG 렌더링 검증 통과')
from main import ElevatorApp
class Screen:
    def __init__(self,w,h):self.w=w;self.h=h
    def winfo_screenwidth(self):return self.w
    def winfo_screenheight(self):return self.h
class App:
    pass
app=App()
for w,h in ((1920,1080),(1366,768),(1024,768)):
    app.root=Screen(w,h)
    result=ElevatorApp._window_size_for_preset(app,'자동')
    assert result[0]<=w-24 and result[1]<=h-72
assert ElevatorApp._window_size_for_preset(type('A',(),{'root':Screen(1920,1080)})(),'자동')==(1280,900)
print('자동 창 크기 및 화면 경계 검증 통과')

app.root=Screen(1920,1080)
assert ElevatorApp._window_size_for_preset(app,'PC 1000×680')==(1200,840)
app.root=Screen(1024,768)
assert ElevatorApp._window_size_for_preset(app,'PC 1000×680')==(1000,696)
print('기존 작은 화면 설정의 확대 및 물리 화면 제한 확인')

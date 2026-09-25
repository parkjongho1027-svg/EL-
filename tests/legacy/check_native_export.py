"""Pillow가 없는 Windows 빌드와 같은 PNG 저장 경로를 검사한다."""
import builtins
import tempfile
from pathlib import Path
import main
from src.ui import scurve_panel
from src.core.elevator_review_engine import scurve_profile
from src.ui.native_plot import render_png

p=scurve_profile(30,2,1,.8,1500)
data=render_png(p,{'surface':'#ffffff','text':'#222222','accent':'#2879cc'})
assert data[:8]==b'\x89PNG\r\n\x1a\n'
class Panel:
    _profile=p
    _energy_profile=None
    _reference_energy_profile=None
panel=Panel()
old_import=builtins.__import__
old_theme=scurve_panel.get_theme
old_dialog=main.filedialog.asksaveasfilename
old_info=main.messagebox.showinfo
old_error=main.messagebox.showerror
errors=[]
def no_pillow(name,*args,**kwargs):
    if name=='plot_render':raise ImportError('No module named PIL')
    return old_import(name,*args,**kwargs)
try:
    with tempfile.TemporaryDirectory() as folder:
        output=Path(folder)/'simulation.png'
        builtins.__import__=no_pillow
        scurve_panel.get_theme=lambda _panel:('light',{'surface':'#ffffff','text':'#222222','accent':'#2879cc'})
        main.filedialog.asksaveasfilename=lambda **_kwargs:str(output)
        main.messagebox.showinfo=lambda *_args,**_kwargs:None
        main.messagebox.showerror=lambda *args,**_kwargs:errors.append(args)
        main.SCurvePanel._save_simulation_png(panel,'mechanical')
        assert output.exists() and output.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        assert not errors,errors
finally:
    builtins.__import__=old_import
    scurve_panel.get_theme=old_theme
    main.filedialog.asksaveasfilename=old_dialog
    main.messagebox.showinfo=old_info
    main.messagebox.showerror=old_error
print('Pillow 없는 PNG 저장 경로 확인')

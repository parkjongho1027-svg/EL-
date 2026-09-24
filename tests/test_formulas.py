"""독립 계산값과 경계 입력에 대한 pytest 회귀 테스트."""
import math

import pytest

from calculators import (calculate_motor_value, calculate_traction_values,
                         calculate_brake_values, calculate_traffic_values)
from energy_model import EnergyTripInput, estimate_trip
from elevator_review_engine import scurve_profile
from errors import CalculationInputError, SimulationLimitError


@pytest.mark.parametrize('target,expected', [('P',30.330882352941178),('Q',1500),('V',180)])
def test_motor_forward_and_inverse(target, expected):
    values={'P':30.330882352941178,'Q':1500,'V':180,'OB':.45,'eff':.8}
    values.pop(target)
    assert calculate_motor_value(target,values)==pytest.approx(expected)


def test_traction_both_sides_and_integer_rope():
    raw=dict(Q=1500,Wc=2400,H=50,wr=1.1,n=6,OB=45,Wcomp=0,Wm=0)
    result=calculate_traction_values(raw)
    assert result['rope_total']==pytest.approx(330)
    assert result['front']==pytest.approx(4230/3075)
    assert result['rear']==pytest.approx(3405/2400)
    assert result['final']==result['rear']
    with pytest.raises(CalculationInputError,match='정수'):
        calculate_traction_values(raw|{'n':6.5})


@pytest.mark.parametrize('pair', [{'v':3,'t':.6},{'v':3,'d':.9},{'d':.9,'a':5}])
def test_brake_independent_pairs(pair):
    result=calculate_brake_values(**pair)
    for key,expected in (('v',3),('t',.6),('d',.9),('a',5)):
        assert result[key]==pytest.approx(expected)
    assert result['consistent']


def test_traffic_hand_computed_single_floor():
    values=dict(A=100,F=3,S=10,phi=.1,C=1,board_rate=1,n=1,
                td=4,tp=2,Tr_travel=60)
    result=calculate_traffic_values(values)
    assert result['round_trip']==pytest.approx(66.6)
    assert result['capacity']==pytest.approx(300/66.6)
    assert result['recommended']==1


@pytest.mark.parametrize('bad', [0, float('nan'),float('inf'),True,'wrong'])
def test_motor_rejects_invalid_efficiency(bad):
    with pytest.raises(CalculationInputError):
        calculate_motor_value('P',dict(Q=1500,V=180,OB=.45,eff=bad))


def test_energy_dataclass_and_sample_budget():
    raw=dict(distance=30,vmax=2,amax=1,jerk=.8,car_mass=1000,
        load_mass=500,counterweight_mass=1500,equivalent_extra_mass=300,
        resistance=100,direction='상승',drive_efficiency=.85,
        regen_efficiency=.5,auxiliary_kw=.15,step=.05)
    assert EnergyTripInput.validate(**raw).distance==30
    assert estimate_trip(**{key:value for key,value in raw.items() if key!='step'})['net_kwh']>0
    for invalid in (math.nan, True, -10):
        with pytest.raises(CalculationInputError):
            EnergyTripInput.validate(**(raw|{'car_mass':invalid}))
    with pytest.raises(SimulationLimitError,match='20,000'):
        scurve_profile(50000,2,1,.8,1500,step=.05)

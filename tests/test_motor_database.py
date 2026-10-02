import pytest
from src.core.motor_database import validate_motor_record, motor_matches
from src.core.errors import CalculationInputError


def motor(power=15, torque=400):
    return {"maker":"Test Maker","model":"M15","rated_power_kw":power,"rated_torque_nm":torque,
            "rated_speed_rpm":400,"inertia_kg_m2":2,"source":"catalog p.1","verified_date":"2026-09-25"}


def test_validate_motor_record():
    row=validate_motor_record(motor())
    assert row["rated_power_kw"] == 15.0


def test_missing_provenance_rejected():
    row=motor(); row["source"]=""
    with pytest.raises(CalculationInputError): validate_motor_record(row)


def test_motor_match_checks_torque():
    rows=[{"payload":motor(15,400)},{"payload":motor(18.5,500)}]
    assert motor_matches(rows,15,350)[0]["torque_ok"] is True
    assert motor_matches(rows,15,450)[0]["torque_ok"] is False


def test_optional_manufacturer_fields_can_be_unknown():
    row=motor(); row["rated_torque_nm"]=None; row["rated_speed_rpm"]=None; row["inertia_kg_m2"]=None
    result=validate_motor_record(row)
    assert result["rated_torque_nm"] is None
    assert result["rated_speed_rpm"] is None
    assert result["inertia_kg_m2"] is None


def test_aliases_from_external_seed_are_accepted():
    row=motor(); row["manufacturer"]=row.pop("maker"); row["rotor_inertia_kg_m2"]=row.pop("inertia_kg_m2")
    result=validate_motor_record(row)
    assert result["maker"] == "Test Maker"
    assert result["inertia_kg_m2"] == 2.0


def test_unknown_torque_is_not_false_failure():
    row=motor(); row["rated_torque_nm"]=None
    match=motor_matches([{"payload":row}],15,450)[0]
    assert match["torque_ok"] is None
    assert match["torque_status"] == "unknown"

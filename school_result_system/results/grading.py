from django.conf import settings


def _fallback_config():
    return {
        "a": 70,
        "b": 60,
        "c": 50,
        "d": 45,
        "pass_mark": 45,
    }


def get_grading_config():
    config = _fallback_config()
    try:
        from accounts.models import SchoolBranding

        brand = SchoolBranding.get_solo()
        config = {
            "a": brand.grade_a_min,
            "b": brand.grade_b_min,
            "c": brand.grade_c_min,
            "d": brand.grade_d_min,
            "pass_mark": brand.pass_mark,
        }
    except Exception:
        pass
    return config


def grade_from_score(score):
    cfg = get_grading_config()
    if score >= cfg["a"]:
        return "A"
    if score >= cfg["b"]:
        return "B"
    if score >= cfg["c"]:
        return "C"
    if score >= cfg["d"]:
        return "D"
    return "F"


def grade_key_text():
    cfg = get_grading_config()
    return (
        f"A:{cfg['a']}-100  "
        f"B:{cfg['b']}-{cfg['a'] - 1}  "
        f"C:{cfg['c']}-{cfg['b'] - 1}  "
        f"D:{cfg['d']}-{cfg['c'] - 1}  "
        f"F:0-{cfg['d'] - 1}"
    )


def pass_mark():
    return get_grading_config()["pass_mark"]

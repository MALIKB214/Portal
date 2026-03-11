from .services import (
    compute_pass_fail,
    get_grade_policy,
    grade_from_score,
    grade_key_text,
    pass_mark,
)


def get_grading_config():
    policy = get_grade_policy()
    return {
        "a": policy.grade_a_min,
        "b": policy.grade_b_min,
        "c": policy.grade_c_min,
        "d": policy.grade_d_min,
        "pass_mark": policy.pass_mark,
    }

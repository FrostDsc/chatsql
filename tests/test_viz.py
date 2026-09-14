"""图表推断单测。"""
from chatsql.viz import infer_chart


class TestInferChart:
    def test_two_cols_text_numeric_is_bar(self):
        cols = ["major", "cnt"]
        rows = [("CS", 5), ("EE", 3), ("Law", 2)]
        assert infer_chart(cols, rows) == "bar"

    def test_date_first_col_is_line(self):
        cols = ["year", "revenue"]
        rows = [("2019", 10), ("2020", 12), ("2021", 15)]
        assert infer_chart(cols, rows) == "line"
        rows_dt = [("2020-01-01", 10), ("2020-02-01", 12)]
        assert infer_chart(cols, rows_dt) == "line"

    def test_numeric_strings_accepted(self):
        rows = [("a", "5"), ("b", "3")]
        assert infer_chart(["k", "v"], rows) == "bar"

    def test_no_chart_cases(self):
        assert infer_chart(["a"], [(1,), (2,)]) == "none"                       # 单列
        assert infer_chart(["a", "b", "c"], [(1, 2, 3), (4, 5, 6)]) == "none"  # 三列
        assert infer_chart(["a", "b"], []) == "none"                           # 0 行
        assert infer_chart(["a", "b"], [("x", 1)]) == "none"                   # 1 行
        assert infer_chart(["a", "b"], [("x", 1)] * 31) == "none"              # 超 30 行
        assert infer_chart(["a", "b"], [("x", "文本"), ("y", "值")]) == "none"  # 第二列非数值

    def test_mixed_date_and_text_is_bar(self):
        rows = [("2020", 3), ("未知年份", 5)]
        assert infer_chart(["y", "c"], rows) == "bar"

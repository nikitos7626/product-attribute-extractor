"""
Скрипт для предварительного рендеринга и валидации ячеек Jupyter Notebook (EDA).
Выполняет код всех ячеек и сохраняет результаты (stdout, HTML-таблицы pandas, метрики)
непосредственно в notebooks/eda_mvideo_dataset.ipynb, обеспечивая идеальное отображение
в интерфейсах GitHub, GitLab, Gitea и JupyterLab без необходимости локального запуска.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass



def execute_notebook(nb_path: Path) -> None:
    with open(nb_path, "r", encoding="utf-8") as f:
        nb = json.load(f)

    # Общее окружение для ячеек
    global_env: dict = {
        "__name__": "__main__",
        "__file__": str(nb_path),
    }

    exec_counter = 1

    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue

        raw_source = cell.get("source", [])
        if isinstance(raw_source, list):
            code_str = "".join(raw_source)
        else:
            code_str = str(raw_source)

        # Автоматическая корректировка BASE_DIR для универсального запуска
        if "BASE_DIR = Path(\"..\").resolve()" in code_str:
            code_str = code_str.replace(
                "BASE_DIR = Path(\"..\").resolve()",
                "cur = Path.cwd()\n"
                "BASE_DIR = cur if (cur / 'data' / 'gold_dataset.json').exists() "
                "else (cur.parent if (cur.parent / 'data' / 'gold_dataset.json').exists() else Path('..').resolve())"
            )
            cell["source"] = [line + "\n" for line in code_str.split("\n")[:-1]] + [code_str.split("\n")[-1]]

        cell["execution_count"] = exec_counter
        cell["outputs"] = []

        stdout_buf = io.StringIO()
        result_value = None

        try:
            # Разбираем AST, чтобы выделить финальное выражение (expression statement) для execute_result
            tree = ast.parse(code_str)
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                last_expr = tree.body.pop()
                exec_code = compile(tree, filename="<cell>", mode="exec")
                eval_code = compile(ast.Expression(last_expr.value), filename="<cell>", mode="eval")

                with contextlib.redirect_stdout(stdout_buf):
                    exec(exec_code, global_env)
                    result_value = eval(eval_code, global_env)
            else:
                exec_code = compile(tree, filename="<cell>", mode="exec")
                with contextlib.redirect_stdout(stdout_buf):
                    exec(exec_code, global_env)

        except Exception as e:
            print(f"[ERROR] Ошибка выполнения ячейки {exec_counter}: {e}", file=sys.stderr)
            cell["outputs"].append({
                "ename": type(e).__name__,
                "evalue": str(e),
                "output_type": "error",
                "traceback": [f"{type(e).__name__}: {e}"],
            })
            continue

        # Сохраняем stdout
        out_text = stdout_buf.getvalue()
        if out_text:
            lines = [line + "\n" for line in out_text.split("\n")[:-1]]
            if out_text.endswith("\n"):
                pass
            else:
                lines.append(out_text.split("\n")[-1])
            cell["outputs"].append({
                "name": "stdout",
                "output_type": "stream",
                "text": lines,
            })

        # Сохраняем результат выражения (DataFrame, Series, etc.)
        if result_value is not None:
            data_dict: dict = {}
            if hasattr(result_value, "to_html"):
                data_dict["text/html"] = [result_value.to_html()]
            data_dict["text/plain"] = [repr(result_value)]

            cell["outputs"].append({
                "data": data_dict,
                "execution_count": exec_counter,
                "metadata": {},
                "output_type": "execute_result",
            })

        exec_counter += 1

    with open(nb_path, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)

    print(f"✅ Ноутбук успешно выполнен и сохранен с выводом всех ячеек: {nb_path}")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    nb_file = repo_root / "notebooks" / "eda_mvideo_dataset.ipynb"
    execute_notebook(nb_file)

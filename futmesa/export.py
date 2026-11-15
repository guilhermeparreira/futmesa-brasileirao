"""Save the tables as Parquet and Excel, and merge new years into an existing base."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .transform import RANKING_COLUMNS, sort_rankings

RANKINGS_PARQUET = "classificacao.parquet"
CHAMPIONSHIPS_PARQUET = "campeonatos.parquet"
PEOPLE_PARQUET = "botonistas.parquet"
EXCEL_FILE = "campeonato_brasileiro_12_toques.xlsx"

DATA_DICTIONARY = {
    "ano": "Ano do campeonato",
    "edicao": "Número da edição do Campeonato Brasileiro Individual (1 = 1989)",
    "cidade_campeonato": "Cidade-sede",
    "uf_campeonato": "UF da cidade-sede",
    "local_campeonato": "Clube/local de disputa (quando o PDF informa)",
    "data_inicio": "Primeiro dia de disputa (quando o PDF informa)",
    "data_fim": "Último dia de disputa (quando o PDF informa)",
    "participantes_informados": "Total de botonistas citado no texto do PDF (só em campeonatos)",
    "categoria": "Adulto, Master, Sub-20, Sub-18, Sub-15 ou Infantil. Até 1992 só havia a categoria "
    "aberta (aqui Adulto), dividida em séries Ouro/Prata/Bronze, mais a Sub-18 a partir de 1990",
    "divisao": "Ouro, Prata, Bronze, Extra, Copa, 1ª a 5ª Divisão, ou Única quando a categoria "
    "não teve divisões",
    "divisao_nivel": "Nível da divisão na categoria/ano (1 = principal). Ouro>Prata>Bronze>Extra>Copa; "
    "Nª Divisão = N; Única = 1",
    "secao_original": "Título da tabela exatamente como no PDF (ex.: 'ADULTO – Copa Santos')",
    "posicao": "Classificação final na divisão; vazio para participante citado sem colocação",
    "botonista": "Nome do botonista como impresso, sem clube, UF e apelido",
    "apelido": "Apelido entre aspas no PDF (ex.: Rubinho)",
    "botonista_chave": "Nome sem acentos/pontuação, em maiúsculas — apoio para unificar o mesmo "
    "botonista entre anos",
    "botonista_padronizado": "Nome após o de-para aprovado (dados/depara_botonistas.csv); sem regra, "
    "repete o nome impresso",
    "id_botonista": "Identificador da pessoa (nome padronizado + UF da estreia), o mesmo em todos "
    "os anos, mesmo quando muda de estado; calculado sobre a base inteira",
    "clube_padronizado": "Clube após o de-para aprovado (dados/depara_clubes.csv)",
    "clube": "Clube entre parênteses (anos iniciais), após o traço (2008) ou sigla (2002 Sub-18/15)",
    "cidade_botonista": "Cidade do clube quando vem no formato '(Clube – Cidade)'",
    "uf_botonista": "UF pela qual o botonista jogou",
    "wo": "Verdadeiro quando a linha traz a marca (WO)",
    "jogos": "J – jogos disputados",
    "vitorias": "V – vitórias",
    "empates": "E – empates",
    "derrotas": "D – derrotas",
    "gols_pro": "GF/GP – gols marcados",
    "gols_contra": "GC – gols sofridos",
    "saldo_gols": "SG – saldo de gols",
    "pontos": "PG – pontos ganhos",
    "observacao": "Correção manual aplicada à linha (ver dados/correcoes_texto.csv)",
    "pagina_pdf": "Página do PDF de onde a linha foi extraída",
    "linha_original": "Texto da linha no PDF, para auditoria",
}


def read_base(output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Load the rankings and championships saved earlier, if they exist."""
    rankings_path = output_dir / RANKINGS_PARQUET
    championships_path = output_dir / CHAMPIONSHIPS_PARQUET
    if not rankings_path.exists() or not championships_path.exists():
        return None
    return pd.read_parquet(rankings_path), pd.read_parquet(championships_path)


def merge_years(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Replace the years present in ``new`` and keep every other year of ``existing``.

    Re-running the update for the same year is therefore idempotent.

    Args:
        existing: Table already saved (rankings or championships).
        new: Table with the years just extracted.

    Returns:
        Combined table, sorted.

    Raises:
        ValueError: If the two tables do not have the same columns.
    """
    if list(existing.columns) != list(new.columns):
        raise ValueError(
            "Colunas diferentes entre a base existente e os novos dados: "
            f"{sorted(set(existing.columns) ^ set(new.columns))}"
        )
    kept = existing[~existing["ano"].isin(new["ano"].unique())]
    combined = pd.concat([kept, new.astype(existing.dtypes.to_dict())], ignore_index=True)
    if list(combined.columns) == RANKING_COLUMNS:
        return sort_rankings(combined)
    return combined.sort_values("ano", ignore_index=True)


def save_base(
    output_dir: Path,
    rankings: pd.DataFrame,
    championships: pd.DataFrame,
    issues: pd.DataFrame,
    extra_sheets: dict[str, pd.DataFrame] | None = None,
) -> list[Path]:
    """Write the Parquet files and the Excel workbook.

    The workbook has four sheets: ``classificacao`` (one row per placing),
    ``campeonatos`` (one row per edition), ``qualidade`` (findings of the
    quality checks) and ``dicionario`` (column descriptions).

    Args:
        output_dir: Folder for the output files (created if needed).
        rankings: Final ranking table.
        championships: Championship table.
        issues: Quality-check findings.
        extra_sheets: Additional workbook sheets (e.g. the de-para tables).

    Returns:
        Paths of the files written.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    rankings_path = output_dir / RANKINGS_PARQUET
    championships_path = output_dir / CHAMPIONSHIPS_PARQUET
    excel_path = output_dir / EXCEL_FILE
    rankings.to_parquet(rankings_path, index=False)
    championships.to_parquet(championships_path, index=False)
    _write_excel(excel_path, rankings, championships, issues, extra_sheets or {})
    return [rankings_path, championships_path, excel_path]


def _write_excel(
    path: Path,
    rankings: pd.DataFrame,
    championships: pd.DataFrame,
    issues: pd.DataFrame,
    extra_sheets: dict[str, pd.DataFrame],
) -> None:
    sheets = {
        "classificacao": rankings,
        "campeonatos": championships,
        "qualidade": issues,
        "dicionario": _dictionary_table(),
        **extra_sheets,
    }
    with pd.ExcelWriter(path, engine="xlsxwriter", datetime_format="dd/mm/yyyy") as writer:
        for name, table in sheets.items():
            table.to_excel(writer, sheet_name=name, index=False)
            _format_sheet(writer, name, table)


def _dictionary_table() -> pd.DataFrame:
    return pd.DataFrame(
        {"coluna": list(DATA_DICTIONARY), "descricao": list(DATA_DICTIONARY.values())}
    )


def _format_sheet(writer: pd.ExcelWriter, name: str, table: pd.DataFrame) -> None:
    """Freeze the header, add filters and size columns to their content."""
    sheet = writer.sheets[name]
    sheet.freeze_panes(1, 0)
    if len(table.columns):
        sheet.autofilter(0, 0, max(len(table), 1), len(table.columns) - 1)
    for index, column in enumerate(table.columns):
        sample = table[column].astype("string").fillna("").head(2000)
        width = max([len(str(column)), *sample.str.len().tolist()])
        sheet.set_column(index, index, min(width + 2, 60))

import os
import re
import sys
import json

import fitz
import pytesseract
from PIL import Image
from tqdm import tqdm

SETORES = {
    "SEMS",
    "SEDUC",
    "SEMOSP",
    "SEFIN",
    "SARH",
    "SECOM",
    "SEDEC",
    "SEMAP",
    "SEMOB",
    "SESP",
    "SEMCI",
    "SEDESO",
    "SEGOV",
    "PGM",
    "SEMMADA",
    "SEPLAN",
    "SESMT",
    "SELTC",
}

# ============================================================
# CONFIGURAÇÕES
# ============================================================

PASTA_PROJETO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

CAMINHO_TESSERACT = os.path.join(
    PASTA_PROJETO,
    "tesseract",
    "tesseract.exe"
)

pytesseract.pytesseract.tesseract_cmd = CAMINHO_TESSERACT

ARQUIVO_CACHE = os.path.join(
    PASTA_PROJETO,
    "cache.json"
)

# ============================================================
# CACHE
# ============================================================

def carregar_cache():

    if not os.path.exists(ARQUIVO_CACHE):
        return {}

    try:

        with open(
            ARQUIVO_CACHE,
            "r",
            encoding="utf-8"
        ) as arquivo:

            return json.load(arquivo)

    except (json.JSONDecodeError, OSError):

        return {}


def salvar_cache(cache):

    with open(
        ARQUIVO_CACHE,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            cache,
            arquivo,
            ensure_ascii=False,
            indent=4
        )


def arquivo_foi_alterado(caminho_pdf, dados_cache):

    informacoes = os.stat(caminho_pdf)

    return (
        dados_cache.get("tamanho") != informacoes.st_size
        or
        dados_cache.get("modificado") != informacoes.st_mtime
    )

# ============================================================
# OCR
# ============================================================

def extrair_texto_pdf(caminho_pdf, nome_esperado):

    documento = fitz.open(caminho_pdf)

    nome_esperado = normalizar_texto(nome_esperado)

    for pagina in documento:

        # Renderiza a página
        imagem = pagina.get_pixmap(dpi=300)

        # Converte para PIL
        imagem_pil = Image.frombytes(
            "RGB",
            [imagem.width, imagem.height],
            imagem.samples
        )

        # ====================================================
        # RECORTE: SOMENTE OS 40% SUPERIORES DA PÁGINA
        # ====================================================

        limite = int(imagem_pil.height * 0.50)

        imagem_pil = imagem_pil.crop(
            (
                0,
                0,
                imagem_pil.width,
                limite
            )
        )

        # ====================================================
        # OCR
        # ====================================================

        texto_pagina = pytesseract.image_to_string(
            imagem_pil,
            lang="por"
        )

        texto_normalizado = normalizar_texto(
            texto_pagina
        )

        # ====================================================
        # VERIFICA NOME
        # ====================================================

        nome_encontrado = (
            nome_esperado in texto_normalizado
        )

        # ====================================================
        # VERIFICA SETOR
        # ====================================================

        setor_encontrado = extrair_setor_do_pdf(
            texto_pagina
        )

        # ====================================================
        # ENCONTROU OS DOIS → PRÓXIMO PDF
        # ====================================================

        if nome_encontrado and setor_encontrado:

            documento.close()

            return texto_pagina

    documento.close()

    return ""


# ============================================================
# NOME DO ARQUIVO
# ============================================================

def extrair_informacoes_nome_arquivo(nome_arquivo):

    padrao = (
        r"^(PA|CAT)\s*-\s*"
        r"(.+?)\s*-\s*"
        r"(?:(.+?)\s*-\s*)?"
        r"(\d{1,2}[.-]\d{1,2}[.-]\d{2,4})"
        r"\s+[Aa]\s+"
        r"(\d{1,2}[.-]\d{1,2}[.-]\d{2,4})"
        r"(?:\s*-\s*.*)?"
        r"\.pdf$"
    )

    resultado = re.match(
        padrao,
        nome_arquivo,
        re.IGNORECASE
    )

    if not resultado:
        return None

    tipo = resultado.group(1)
    nome = resultado.group(2)
    setor = resultado.group(3)

    return {
        "tipo": tipo.upper(),
        "nome": nome.strip(),
        "setor": setor.strip() if setor else None,
        "data_inicio": resultado.group(4),
        "data_fim": resultado.group(5)
    }


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar_texto(texto):

    texto = texto.upper()

    substituicoes = {
        "Á": "A",
        "À": "A",
        "Ã": "A",
        "Â": "A",
        "É": "E",
        "Ê": "E",
        "Í": "I",
        "Ó": "O",
        "Ô": "O",
        "Õ": "O",
        "Ú": "U",
        "Ç": "C"
    }

    for original, substituto in substituicoes.items():
        texto = texto.replace(original, substituto)

    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


# ============================================================
# LOCALIZAÇÃO DO NOME
# ============================================================

def encontrar_nome_no_texto(nome_esperado, texto_pdf):

    texto = normalizar_texto(texto_pdf)
    nome = normalizar_texto(nome_esperado)

    if nome in texto:
        return nome

    return None


# ============================================================
# LOCALIZAÇÃO DO SETOR
# ============================================================

def extrair_setor_do_pdf(texto_pdf):

    texto = normalizar_texto(texto_pdf)

    padrao = (
        r"SECRETARIA\s+DE\s+LOTACAO\s*:\s*(.*)"
    )

    resultado = re.search(
        padrao,
        texto
    )

    if not resultado:
        return None

    informacao = resultado.group(1)

    # ========================================================
    # PROCURA UMA SIGLA OFICIAL
    # ========================================================

    for setor in SETORES:

        if re.search(
            rf"\b{re.escape(setor)}\b",
            informacao
        ):
            return setor

    # ========================================================
    # NOMES COMPLETOS DAS SECRETARIAS
    # ========================================================

    conversoes = {
        "SECRETARIA DE GOVERNO": "SEGOV",
    }

    for nome_secretaria, sigla in conversoes.items():

        if nome_secretaria in informacao:
            return sigla

    return None


# ============================================================
# PROCESSAMENTO
# ============================================================

def processar_pdf(caminho_pdf):

    nome_arquivo = os.path.basename(caminho_pdf)

    informacoes = extrair_informacoes_nome_arquivo(
        nome_arquivo
    )

    if informacoes is None:
        return {
            "status": "fora_padrao",
            "arquivo": nome_arquivo
        }

    texto_pdf = extrair_texto_pdf(
        caminho_pdf,
        informacoes["nome"]
    )

    nome_encontrado = encontrar_nome_no_texto(
        informacoes["nome"],
        texto_pdf
    )

    setor_encontrado = extrair_setor_do_pdf(
        texto_pdf
    )

    nome_correto = nome_encontrado is not None

    if informacoes["setor"]:

        setor_correto = (
            setor_encontrado is not None
            and normalizar_texto(informacoes["setor"])
            == normalizar_texto(setor_encontrado)
        )

    else:

        setor_correto = True

    if nome_correto and setor_correto:
        return {
            "status": "correto"
        }

    return {
        "status": "divergente",
        "arquivo": nome_arquivo,
        "nome_esperado": informacoes["nome"],
        "nome_encontrado": nome_encontrado,
        "setor_esperado": informacoes["setor"],
        "setor_encontrado": setor_encontrado
    }


# ============================================================
# MAIN
# ============================================================

def main():

    if len(sys.argv) != 2:
        print('Uso: python src/main.py "pasta_com_os_pdfs"')
        return

    pasta_pdfs = sys.argv[1]

    if not os.path.isdir(pasta_pdfs):
        print("Pasta não encontrada.")
        return

    pdfs = []

    for raiz, pastas, arquivos in os.walk(pasta_pdfs):

        for arquivo in arquivos:

            if arquivo.lower().endswith(".pdf"):

                caminho_pdf = os.path.join(
                    raiz,
                    arquivo
                )

                pdfs.append(caminho_pdf)

    if not pdfs:
        print("Nenhum PDF encontrado.")
        return

    cache = carregar_cache()

    resultados = {
        "correto": 0,
        "divergente": 0,
        "fora_padrao": 0
    }

    divergencias = []
    fora_padrao = []

    for caminho_pdf in tqdm(
        pdfs,
        desc="Processando",
        unit="pdf"
    ):

        informacoes_arquivo = os.stat(
            caminho_pdf
        )

        chave = os.path.abspath(
            caminho_pdf
        )

        dados_cache = cache.get(chave)

        # ========================================================
        # VERIFICA SE JÁ EXISTE NO CACHE E NÃO FOI ALTERADO
        # ========================================================

        if (
            dados_cache is not None
            and not arquivo_foi_alterado(
                caminho_pdf,
                dados_cache
            )
        ):

            resultado = dados_cache["resultado"]

        # ========================================================
        # PDF NOVO OU ALTERADO → PROCESSA NORMALMENTE
        # ========================================================

        else:

            resultado = processar_pdf(
                caminho_pdf
            )

            # ========================================================
            # SALVA NO CACHE SOMENTE SE ESTIVER TUDO CORRETO
            # ========================================================

            if resultado["status"] == "correto":

                cache[chave] = {
                    "tamanho": informacoes_arquivo.st_size,
                    "modificado": informacoes_arquivo.st_mtime,
                    "resultado": resultado
                }

        resultados[
            resultado["status"]
        ] += 1

        if resultado["status"] == "divergente":

            divergencias.append(
                resultado
            )

        elif resultado["status"] == "fora_padrao":

            fora_padrao.append(
                resultado["arquivo"]
            )

    # ========================================================
    # SALVA O CACHE
    # ========================================================

    salvar_cache(cache)

    # ========================================================
    # RESULTADO
    # ========================================================

    print(
        f"\n✓ {resultados['correto']} corretos"
    )

    if divergencias:

        print(
            f"✗ {resultados['divergente']} divergente(s):"
        )

        for divergencia in divergencias:

            print(
                f"\n  Arquivo: "
                f"{divergencia['arquivo']}"
            )

            print(
                f"  Nome: "
                f"{divergencia['nome_esperado']} "
                f"→ "
                f"{divergencia['nome_encontrado'] or 'não encontrado'}"
            )

            print(
                f"  Setor: "
                f"{divergencia['setor_esperado']} "
                f"→ "
                f"{divergencia['setor_encontrado'] or 'não encontrado'}"
            )

    if fora_padrao:

        print(
            f"\n⚠ {resultados['fora_padrao']} "
            f"fora do padrão:"
        )

        for arquivo in fora_padrao:
            print(f"  {arquivo}")


if __name__ == "__main__":
    main()
"""
calculadoras/services_sueldo.py — Cálculo de sueldo líquido en Chile.

Fórmula (trabajador dependiente, contrato indefinido):
    1. Renta imponible = min(bruto, tope_imponible)
    2. AFP   = renta_imponible * (0.10 + comision_afp)
    3. Salud = renta_imponible * 0.07           (Fonasa)
             o monto fijo en UF                 (Isapre — el usuario lo declara)
    4. Cesantía = renta_imponible * 0.006        (indefinido)
    5. Base IGC = bruto - AFP - salud - cesantía
    6. IGC = aplicar tramos sobre base_IGC / UTM
    7. Líquido = bruto - AFP - salud - cesantía - IGC

Notas:
    - Para Isapre el monto se entrega en UF y se convierte con UF_VALOR_REFERENCIAL.
      Esto es una aproximación; el cálculo "real" lo hace la Isapre con la UF del mes.
    - No incluimos asignaciones (colación, movilización, bono) ni aportes
      adicionales (APV). Es una calc "estándar".
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

from config.tributario import (
    AFP_CARGO_EMPLEADOR,
    AFP_COTIZACION_OBLIGATORIA,
    GRATIFICACION_LEGAL_TASA,
    GRATIFICACION_LEGAL_TOPE_IMM_ANUAL,
    IGC_TRAMOS_2026,
    INGRESO_MINIMO_MENSUAL,
    MUTUAL_TASA_BASE,
    SALUD_FONASA,
    SEGURO_CESANTIA_EMPLEADOR_INDEFINIDO,
    SEGURO_CESANTIA_EMPLEADOR_PLAZO_FIJO,
    SEGURO_CESANTIA_INDEFINIDO,
    SEGURO_CESANTIA_PLAZO_FIJO,
    SIS_TASA,
    TOPE_CESANTIA_UF,
    TOPE_IMPONIBLE_UF,
)
from core.services.mindicador import get_uf, get_utm

_CLP_QUANTIZER: Final = Decimal("1")


@dataclass(frozen=True, slots=True)
class ResultadoSueldo:
    bruto: Decimal
    renta_imponible: Decimal     # con tope aplicado
    afp_total: Decimal           # 10% + comisión
    afp_obligatoria: Decimal     # solo el 10%
    afp_comision: Decimal        # solo la comisión
    afp_comision_pct: Decimal    # % aplicado (para display en PDF/UI)
    salud: Decimal
    salud_tipo: str              # "fonasa" | "isapre"
    cesantia: Decimal
    cesantia_pct: Decimal        # % aplicado (0 o 0.6%)
    base_igc: Decimal            # bruto - AFP - salud - cesantía
    igc: Decimal                 # impuesto único
    liquido: Decimal
    total_descuentos: Decimal
    modo: str                    # "bruto_a_liquido" | "liquido_a_bruto"
    utm_usada: Decimal           # UTM al momento del cálculo (para auditar PDF)
    uf_usada: Decimal            # UF al momento del cálculo

    # Asignaciones no imponibles (se SUMAN al líquido, no descuentan)
    colacion: Decimal
    movilizacion: Decimal
    gratificacion_legal: Decimal    # 0 si no aplica
    liquido_total: Decimal          # liquido + colacion + movilizacion + gratificacion

    # Costo total empleador (trabajador NO ve, es para info del empresario)
    aporte_afp_empleador: Decimal   # 0.1% sobre renta imponible
    aporte_sis: Decimal             # 1,62% sobre renta imponible
    aporte_mutual: Decimal          # 0,95% sobre renta imponible
    aporte_cesantia_empleador: Decimal  # 2,4% indefinido o 3% plazo fijo
    costo_total_empleador: Decimal  # bruto + asignaciones + todos los aportes


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, str)):
        try:
            return Decimal(str(valor))
        except InvalidOperation as exc:
            raise ValueError(f"Monto inválido: {valor!r}") from exc
    if isinstance(valor, float):
        return Decimal(str(valor))
    raise ValueError(f"Tipo no soportado: {type(valor).__name__}")


def _q(d: Decimal) -> Decimal:
    return d.quantize(_CLP_QUANTIZER, rounding=ROUND_HALF_UP)


def _calcular_igc(base_imponible_clp: Decimal, utm_valor: Decimal) -> Decimal:
    """
    Calcula el Impuesto Único de Segunda Categoría (mensual).

    Pasos:
        1. base_UTM = base_imponible_clp / UTM
        2. ubicar tramo (lim_inf, lim_sup, tasa, rebaja_UTM)
        3. impuesto_UTM = base_UTM * tasa - rebaja_UTM
        4. impuesto_clp = impuesto_UTM * UTM
    """
    if base_imponible_clp <= 0:
        return Decimal("0")

    base_utm = base_imponible_clp / utm_valor

    for lim_inf, lim_sup, tasa, rebaja_utm in IGC_TRAMOS_2026:
        if base_utm >= lim_inf and (lim_sup is None or base_utm < lim_sup):
            impuesto_utm = (base_utm * tasa) - rebaja_utm
            impuesto_clp = impuesto_utm * utm_valor
            return _q(max(Decimal("0"), impuesto_clp))

    return Decimal("0")


def calcular(
    monto,
    *,
    modo: str = "bruto_a_liquido",
    afp_comision=Decimal("0.0104"),
    salud_tipo: str = "fonasa",
    salud_isapre_uf=Decimal("0"),
    contrato: str = "indefinido",
    colacion=Decimal("0"),
    movilizacion=Decimal("0"),
    gratificacion_legal: bool = False,
) -> ResultadoSueldo:
    """
    Args:
        monto:           si modo='bruto_a_liquido': bruto en CLP.
                         si modo='liquido_a_bruto': líquido objetivo en CLP.
        modo:            'bruto_a_liquido' (default) o 'liquido_a_bruto'.
        afp_comision:    comisión adicional de la AFP (ej: 0.0104 = 1.04%).
                         No incluye el 10% obligatorio (ese va aparte).
        salud_tipo:      'fonasa' o 'isapre'.
        salud_isapre_uf: si isapre, plan en UF mensual.
        contrato:        'indefinido' | 'plazo_fijo'.
        colacion:        asignación colación CLP (no imponible, se suma al líquido).
        movilizacion:    asignación movilización CLP (no imponible).
        gratificacion_legal: si True, agrega 25% del sueldo con tope 4,75 IMM/12.
    """
    if modo not in ("bruto_a_liquido", "liquido_a_bruto"):
        raise ValueError(f"Modo inválido: {modo!r}")

    monto_d = _to_decimal(monto)
    if monto_d < 0:
        raise ValueError("El monto no puede ser negativo.")

    # Si el modo es invertido, resolvemos por búsqueda binaria.
    # IMPORTANTE: el "líquido" objetivo del usuario se refiere SOLO al sueldo
    # neto sin asignaciones (colación, movilización, gratificación se suman
    # APARTE al final). Por eso la búsqueda binaria no las considera.
    if modo == "liquido_a_bruto":
        bruto_d = _resolver_bruto_desde_liquido(
            monto_d,
            afp_comision=afp_comision,
            salud_tipo=salud_tipo,
            salud_isapre_uf=salud_isapre_uf,
            contrato=contrato,
        )
    else:
        bruto_d = monto_d

    comision_d = _to_decimal(afp_comision)
    if comision_d < 0 or comision_d > Decimal("0.05"):
        raise ValueError("Comisión AFP fuera de rango razonable.")

    # Valores de indicadores en tiempo real (con fallback hardcoded si la API cae)
    uf_clp = get_uf()
    utm_clp = get_utm()

    # 1. Renta imponible con tope
    tope_clp = TOPE_IMPONIBLE_UF * uf_clp
    renta_imponible = min(bruto_d, tope_clp)

    # 2. AFP
    afp_obligatoria = renta_imponible * AFP_COTIZACION_OBLIGATORIA
    afp_comision_clp = renta_imponible * comision_d
    afp_total = afp_obligatoria + afp_comision_clp

    # 3. Salud
    if salud_tipo == "fonasa":
        salud = renta_imponible * SALUD_FONASA
    elif salud_tipo == "isapre":
        salud_uf = _to_decimal(salud_isapre_uf)
        if salud_uf < 0:
            raise ValueError("Monto Isapre no puede ser negativo.")
        salud = salud_uf * uf_clp
    else:
        raise ValueError(f"salud_tipo inválido: {salud_tipo!r}")

    # 4. Seguro Cesantía — tiene SU PROPIO tope (Ley 19.728), mayor que AFP/Salud.
    if contrato == "indefinido":
        cesantia_pct_d = SEGURO_CESANTIA_INDEFINIDO
        cesantia_emp_pct = SEGURO_CESANTIA_EMPLEADOR_INDEFINIDO
    elif contrato == "plazo_fijo":
        cesantia_pct_d = SEGURO_CESANTIA_PLAZO_FIJO
        cesantia_emp_pct = SEGURO_CESANTIA_EMPLEADOR_PLAZO_FIJO
    else:
        raise ValueError(f"contrato inválido: {contrato!r}")
    tope_cesantia_clp = TOPE_CESANTIA_UF * uf_clp
    base_cesantia = min(bruto_d, tope_cesantia_clp)
    cesantia = base_cesantia * cesantia_pct_d

    # 5. Base imponible IGC
    base_igc = bruto_d - afp_total - salud - cesantia
    base_igc = max(Decimal("0"), base_igc)

    # 6. IGC
    igc = _calcular_igc(base_igc, utm_clp)

    # 7. Líquido (sin asignaciones)
    total_descuentos = afp_total + salud + cesantia + igc
    liquido = bruto_d - total_descuentos

    # 8. Asignaciones no imponibles
    colacion_d = _to_decimal(colacion)
    movilizacion_d = _to_decimal(movilizacion)
    if colacion_d < 0 or movilizacion_d < 0:
        raise ValueError("Asignaciones no pueden ser negativas.")

    # 9. Gratificación legal mensual (Art. 50 Código del Trabajo)
    # min(25% sueldo, 4.75 × IMM / 12). Es IMPONIBLE pero el SII la trata
    # como parte del sueldo bruto — acá la mostramos como "extra" porque
    # algunos contratos la pagan separadamente.
    if gratificacion_legal:
        grat_por_pct = bruto_d * GRATIFICACION_LEGAL_TASA
        grat_tope = (GRATIFICACION_LEGAL_TOPE_IMM_ANUAL * INGRESO_MINIMO_MENSUAL) / Decimal("12")
        gratificacion_clp = min(grat_por_pct, grat_tope)
    else:
        gratificacion_clp = Decimal("0")

    # 10. Líquido total con asignaciones + gratificación
    liquido_total = liquido + colacion_d + movilizacion_d + gratificacion_clp

    # 11. COSTO TOTAL EMPLEADOR
    aporte_afp_emp = renta_imponible * AFP_CARGO_EMPLEADOR
    aporte_sis     = renta_imponible * SIS_TASA
    aporte_mutual  = renta_imponible * MUTUAL_TASA_BASE
    aporte_cesantia_emp = base_cesantia * cesantia_emp_pct
    costo_total_emp = (
        bruto_d
        + colacion_d + movilizacion_d + gratificacion_clp
        + aporte_afp_emp + aporte_sis + aporte_mutual + aporte_cesantia_emp
    )

    return ResultadoSueldo(
        bruto=_q(bruto_d),
        renta_imponible=_q(renta_imponible),
        afp_total=_q(afp_total),
        afp_obligatoria=_q(afp_obligatoria),
        afp_comision=_q(afp_comision_clp),
        afp_comision_pct=comision_d * Decimal("100"),
        salud=_q(salud),
        salud_tipo=salud_tipo,
        cesantia=_q(cesantia),
        cesantia_pct=cesantia_pct_d * Decimal("100"),
        base_igc=_q(base_igc),
        igc=_q(igc),
        liquido=_q(liquido),
        total_descuentos=_q(total_descuentos),
        modo=modo,
        utm_usada=_q(utm_clp),
        uf_usada=_q(uf_clp),
        colacion=_q(colacion_d),
        movilizacion=_q(movilizacion_d),
        gratificacion_legal=_q(gratificacion_clp),
        liquido_total=_q(liquido_total),
        aporte_afp_empleador=_q(aporte_afp_emp),
        aporte_sis=_q(aporte_sis),
        aporte_mutual=_q(aporte_mutual),
        aporte_cesantia_empleador=_q(aporte_cesantia_emp),
        costo_total_empleador=_q(costo_total_emp),
    )


# ── Búsqueda binaria: líquido → bruto ────────────────────────────────────────

def _resolver_bruto_desde_liquido(
    liquido_objetivo: Decimal,
    *,
    afp_comision: Decimal,
    salud_tipo: str,
    salud_isapre_uf: Decimal,
    contrato: str,
    tol: Decimal = Decimal("1"),       # tolerancia 1 CLP
    max_iter: int = 60,
) -> Decimal:
    """
    Invierte el cálculo del sueldo: dado el líquido deseado, encuentra el bruto.

    Como el IGC es por tramos progresivos, la función bruto → líquido es
    monotónica y suave a trozos. Búsqueda binaria converge en ~25 iter.
    """
    if liquido_objetivo <= 0:
        return Decimal("0")

    lo = liquido_objetivo                              # bruto ≥ líquido siempre
    hi = liquido_objetivo * Decimal("3")               # heurística: bruto < 3× líquido
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        r = calcular(
            mid,
            modo="bruto_a_liquido",
            afp_comision=afp_comision,
            salud_tipo=salud_tipo,
            salud_isapre_uf=salud_isapre_uf,
            contrato=contrato,
        )
        diff = r.liquido - liquido_objetivo
        if abs(diff) <= tol:
            return mid
        if diff < 0:
            lo = mid
        else:
            hi = mid
    return mid    # devolvemos la mejor aproximación al llegar al máx iter

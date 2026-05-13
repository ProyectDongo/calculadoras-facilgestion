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
    EXPECTATIVA_VIDA_TASA,
    IGC_TRAMOS_2026,
    INGRESO_MINIMO_MENSUAL,
    ISAPRE_ADICIONAL_TOPE_IGC,
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
from core.services.mindicador import get_uf_liquidacion, get_utm

_CLP_QUANTIZER: Final = Decimal("1")


@dataclass(frozen=True, slots=True)
class ResultadoSueldo:
    # ── Bruto y composición ─────────────────────────────────────
    sueldo_base: Decimal         # lo que ingresó el user (sin gratif)
    gratificacion_legal: Decimal # 25% × sueldo_base con tope, o 0
    bruto: Decimal               # sueldo_base + gratificacion_legal (IMPONIBLE)

    # ── Cálculo ─────────────────────────────────────────────────
    renta_imponible: Decimal     # con tope AFP/Salud aplicado
    afp_total: Decimal           # 10% + comisión
    afp_obligatoria: Decimal
    afp_comision: Decimal
    afp_comision_pct: Decimal
    salud: Decimal
    salud_tipo: str              # "fonasa" | "isapre"
    cesantia: Decimal
    cesantia_pct: Decimal
    base_igc: Decimal            # bruto - AFP - salud - cesantía
    igc: Decimal
    liquido: Decimal             # bruto - todos los descuentos
    total_descuentos: Decimal
    modo: str
    utm_usada: Decimal
    uf_usada: Decimal

    # ── Asignaciones NO imponibles (suman al líquido) ────────
    colacion: Decimal
    movilizacion: Decimal
    liquido_total: Decimal       # liquido + colacion + movilizacion

    # ── Lo que pidió el user (para display fiel) ─────────────
    monto_input: Decimal

    # ── Aportes patronales (cargo del empleador) ────────────
    aporte_afp_empleador: Decimal       # 0,1% sobre renta imponible
    aporte_expectativa_vida: Decimal    # 0,9% (reforma previsional 2025)
    aporte_sis: Decimal                 # 1,62% sobre renta imponible
    aporte_mutual: Decimal              # 0,93% mutual básica
    aporte_cesantia_empleador: Decimal  # 2,4% indefinido / 3% plazo fijo
    aportes_patronales_total: Decimal   # suma de todos los aportes patronales
    costo_total_empleador: Decimal      # aportes patronales + Total Haberes Tributables


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

    comision_d = _to_decimal(afp_comision)
    if comision_d < 0 or comision_d > Decimal("0.05"):
        raise ValueError("Comisión AFP fuera de rango razonable.")

    # Resolver sueldo_base según el modo.
    # IMPORTANTE: la gratificación legal Art. 50 es IMPONIBLE. Se suma al
    # sueldo base ANTES de calcular AFP, salud, cesantía, IGC.
    # Las asignaciones (colación, movilización) NO son imponibles y se
    # consideran solo al final, como suma al líquido.
    if modo == "liquido_a_bruto":
        # El usuario ingresa el LÍQUIDO TOTAL deseado (incluyendo
        # asignaciones no imponibles). Para que el resultado coincida,
        # restamos colación + movilización antes de la búsqueda binaria.
        colacion_pre = _to_decimal(colacion)
        movilizacion_pre = _to_decimal(movilizacion)
        liquido_sin_asign = monto_d - colacion_pre - movilizacion_pre
        if liquido_sin_asign < 0:
            raise ValueError(
                "El líquido objetivo debe ser mayor que la suma de asignaciones."
            )
        sueldo_base = _resolver_sueldo_base_desde_liquido(
            liquido_sin_asign,
            afp_comision=afp_comision,
            salud_tipo=salud_tipo,
            salud_isapre_uf=salud_isapre_uf,
            contrato=contrato,
            gratificacion_legal=gratificacion_legal,
        )
    else:
        sueldo_base = monto_d

    # Indicadores:
    # - UF: la del ÚLTIMO DÍA del mes anterior (regla SII/AFP/Isapre para
    #   liquidaciones). NO la UF de hoy.
    # - UTM: la del mes en curso (sí, la actual).
    uf_clp = get_uf_liquidacion()
    utm_clp = get_utm()

    # Gratificación legal mensual (Art. 50): IMPONIBLE, se suma al sueldo base.
    # min(25% × sueldo_base, 4,75 × IMM / 12)
    if gratificacion_legal:
        grat_por_pct = sueldo_base * GRATIFICACION_LEGAL_TASA
        grat_tope = (GRATIFICACION_LEGAL_TOPE_IMM_ANUAL * INGRESO_MINIMO_MENSUAL) / Decimal("12")
        gratificacion_clp = min(grat_por_pct, grat_tope)
    else:
        gratificacion_clp = Decimal("0")

    bruto_d = sueldo_base + gratificacion_clp   # bruto imponible

    # 1. Renta imponible con tope (sobre bruto incluyendo gratificación)
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

    # 4. Seguro Cesantía — tiene SU PROPIO tope (Ley 19.728), mayor que AFP.
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
    # Rebajan de la base del IGC:
    #   - AFP total (10% obligatorio + comisión)
    #   - Salud 7% del imponible (cotización obligatoria)
    #   - Cesantía trabajador 0,6%
    #   - Si Isapre: la "rebaja adicional Isapre" — Art. 50 ter DL 824 (Ley 21.420):
    #     min(plan_Isapre − 7%, tope mensual). Tope 2026: $62.822/mes.
    salud_obligatoria = renta_imponible * SALUD_FONASA   # 7% del imponible
    if salud_tipo == "isapre":
        adicional_isapre = max(Decimal("0"), salud - salud_obligatoria)
        rebaja_adicional_igc = min(adicional_isapre, ISAPRE_ADICIONAL_TOPE_IGC)
    else:
        rebaja_adicional_igc = Decimal("0")
    base_igc = bruto_d - afp_total - salud_obligatoria - cesantia - rebaja_adicional_igc
    base_igc = max(Decimal("0"), base_igc)

    # 6. IGC
    igc = _calcular_igc(base_igc, utm_clp)

    # 7. Líquido (sin asignaciones no imponibles)
    total_descuentos = afp_total + salud + cesantia + igc
    liquido = bruto_d - total_descuentos

    # 8. Asignaciones NO imponibles
    colacion_d = _to_decimal(colacion)
    movilizacion_d = _to_decimal(movilizacion)
    if colacion_d < 0 or movilizacion_d < 0:
        raise ValueError("Asignaciones no pueden ser negativas.")

    # 9. Líquido total = líquido + asignaciones no imponibles
    liquido_total = liquido + colacion_d + movilizacion_d

    # 10. APORTES PATRONALES (cargo del empleador)
    aporte_afp_emp        = renta_imponible * AFP_CARGO_EMPLEADOR
    aporte_expectativa    = renta_imponible * EXPECTATIVA_VIDA_TASA
    aporte_sis            = renta_imponible * SIS_TASA
    aporte_mutual         = renta_imponible * MUTUAL_TASA_BASE
    aporte_cesantia_emp   = base_cesantia * cesantia_emp_pct
    aportes_patronales_total = (
        aporte_afp_emp + aporte_expectativa + aporte_sis + aporte_mutual + aporte_cesantia_emp
    )
    # Costo total = Aportes patronales + Total Haberes (imponibles + no imponibles)
    costo_total_emp = aportes_patronales_total + bruto_d + colacion_d + movilizacion_d

    return ResultadoSueldo(
        sueldo_base=_q(sueldo_base),
        gratificacion_legal=_q(gratificacion_clp),
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
        liquido_total=_q(liquido_total),
        monto_input=_q(monto_d),
        aporte_afp_empleador=_q(aporte_afp_emp),
        aporte_expectativa_vida=_q(aporte_expectativa),
        aporte_sis=_q(aporte_sis),
        aporte_mutual=_q(aporte_mutual),
        aporte_cesantia_empleador=_q(aporte_cesantia_emp),
        aportes_patronales_total=_q(aportes_patronales_total),
        costo_total_empleador=_q(costo_total_emp),
    )


# ── Búsqueda binaria: líquido → sueldo base ─────────────────────────────────

def _liquido_raw_desde_sueldo_base(
    sueldo_base: Decimal,
    *,
    afp_comision: Decimal,
    salud_tipo: str,
    salud_isapre_uf: Decimal,
    contrato: str,
    gratificacion_legal: bool,
    uf_clp: Decimal,
    utm_clp: Decimal,
) -> Decimal:
    """Igual lógica que calcular(), pero SIN quantize. Devuelve líquido
    (sin asignaciones) como Decimal de precisión arbitraria. Usado por la
    búsqueda binaria para evitar el efecto plateau del redondeo a peso."""
    if gratificacion_legal:
        grat_por_pct = sueldo_base * GRATIFICACION_LEGAL_TASA
        grat_tope = (GRATIFICACION_LEGAL_TOPE_IMM_ANUAL * INGRESO_MINIMO_MENSUAL) / Decimal("12")
        gratificacion_clp = min(grat_por_pct, grat_tope)
    else:
        gratificacion_clp = Decimal("0")
    bruto_d = sueldo_base + gratificacion_clp
    tope_clp = TOPE_IMPONIBLE_UF * uf_clp
    renta_imponible = min(bruto_d, tope_clp)
    afp_total = renta_imponible * (AFP_COTIZACION_OBLIGATORIA + afp_comision)
    if salud_tipo == "fonasa":
        salud = renta_imponible * SALUD_FONASA
    else:
        salud = salud_isapre_uf * uf_clp
    if contrato == "indefinido":
        cesantia_pct_d = SEGURO_CESANTIA_INDEFINIDO
    else:
        cesantia_pct_d = SEGURO_CESANTIA_PLAZO_FIJO
    tope_cesantia_clp = TOPE_CESANTIA_UF * uf_clp
    base_cesantia = min(bruto_d, tope_cesantia_clp)
    cesantia = base_cesantia * cesantia_pct_d
    salud_obligatoria = renta_imponible * SALUD_FONASA
    if salud_tipo == "isapre":
        adicional_isapre = max(Decimal("0"), salud - salud_obligatoria)
        rebaja_adicional_igc = min(adicional_isapre, ISAPRE_ADICIONAL_TOPE_IGC)
    else:
        rebaja_adicional_igc = Decimal("0")
    base_igc = bruto_d - afp_total - salud_obligatoria - cesantia - rebaja_adicional_igc
    base_igc = max(Decimal("0"), base_igc)
    igc = _calcular_igc(base_igc, utm_clp)
    return bruto_d - afp_total - salud - cesantia - igc


def _resolver_sueldo_base_desde_liquido(
    liquido_objetivo: Decimal,
    *,
    afp_comision: Decimal,
    salud_tipo: str,
    salud_isapre_uf: Decimal,
    contrato: str,
    gratificacion_legal: bool,
    tol: Decimal = Decimal("0.01"),
    max_iter: int = 200,
) -> Decimal:
    """Invierte el cálculo: dado el líquido deseado (sin asignaciones),
    encuentra el SUELDO BASE (sin gratificación). Usa _liquido_raw_* sin
    quantize para evitar plateaus de redondeo: la búsqueda converge al peso."""
    if liquido_objetivo <= 0:
        return Decimal("0")

    uf_clp = get_uf_liquidacion()
    utm_clp = get_utm()

    lo = Decimal("0")
    hi = liquido_objetivo * Decimal("3")
    mid = (lo + hi) / 2
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        liquido_calc = _liquido_raw_desde_sueldo_base(
            mid,
            afp_comision=afp_comision,
            salud_tipo=salud_tipo,
            salud_isapre_uf=salud_isapre_uf,
            contrato=contrato,
            gratificacion_legal=gratificacion_legal,
            uf_clp=uf_clp,
            utm_clp=utm_clp,
        )
        diff = liquido_calc - liquido_objetivo
        if abs(diff) <= tol:
            break
        if diff < 0:
            lo = mid
        else:
            hi = mid
    return mid

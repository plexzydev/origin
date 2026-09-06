"""
Interfaz de linea de comandos.

    python -m qtdesk.cli demo          corrida completa sobre el mundo sintetico
    python -m qtdesk.cli voces         una decision con las cinco voces separadas
    python -m qtdesk.cli embudo        por que NO se opera: el embudo completo
    python -m qtdesk.cli factibilidad  R:R alcanzable vs frecuencia objetivo
    python -m qtdesk.cli stress        stress test del libro actual
    python -m qtdesk.cli journal PATH  verifica la cadena de hashes
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from .backtest import metrics as met
from .backtest.engine import BacktestEngine
from .clock import AccessAudit
from .config import SystemConfig
from .contracts import Action, Position, Role, Side, utc
from .data.policy import PolicyCalendar, PolicyEvent, PolicyKind
from .data.providers.synthetic import SECTORS, build_world
from .engine.decision import DecisionEngine, EngineDeps
from .engine.feasibility import analyze, measure_rr_by_horizon
from .learning.error_book import ErrorBook
from .learning.journal import Journal
from .learning.review import ReviewLedger, review_trade
from .learning.reports import monthly
from .risk import stress as stress_mod
from .risk.circuit_breakers import evaluate as breakers
from .risk.frequency import FrequencyGovernor
from .risk.state import DeskState

BANNER = "=" * 78


def _policy_calendar() -> PolicyCalendar:
    pc = PolicyCalendar()
    pc.add(PolicyEvent(PolicyKind.ANTITRUST, "revision antimonopolio del sector", ("TECNOLOGIA",),
                       rumored_at=utc(2021, 3, 1), announced_at=utc(2021, 6, 1),
                       effective_at=date(2022, 1, 1), consensus_prob=0.35,
                       impact_sign=-1, magnitude=0.7))
    pc.add(PolicyEvent(PolicyKind.FISCAL, "paquete de infraestructura", ("INDUSTRIAL", "ENERGIA"),
                       rumored_at=utc(2020, 11, 1), announced_at=utc(2021, 2, 1),
                       consensus_prob=0.5, impact_sign=1, magnitude=0.6))
    pc.add(PolicyEvent(PolicyKind.TARIFF, "aranceles a importaciones energeticas", ("ENERGIA",),
                       rumored_at=utc(2020, 6, 1), consensus_prob=0.25,
                       impact_sign=-1, magnitude=0.5))
    return pc


def _setup(cfg: SystemConfig):
    world = build_world()
    bundle = world.to_bundle()
    gov = FrequencyGovernor(cfg.frequency)
    eng = DecisionEngine(cfg, EngineDeps.default(
        policy_calendar=_policy_calendar(), error_book=ErrorBook(), freq_governor=gov,
    ))
    return world, bundle, eng, gov


# ---------------------------------------------------------------------------

def cmd_voces(args) -> int:
    """Muestra una decision completa con las cinco voces separadas."""
    cfg = SystemConfig()
    world, bundle, eng, _ = _setup(cfg)
    desk = DeskState(equity=100_000.0)
    idx = args.sesion if args.sesion else 560
    as_of = world.sessions[idx]
    ctx = bundle.context(args.simbolo, as_of, desk, cfg, AccessAudit())
    d = eng.decide(ctx, breakers(desk, cfg.risk))

    print(BANNER)
    print(f"  MESA DE TRADING  --  {d.symbol}  --  {as_of.date()}")
    print(BANNER)
    print(f"\nRESULTADO: {d.action.value}")
    print(f"Regimen: {d.regime_cycle.value}/{d.regime_risk.value}")
    print(f"Score combinado: {d.combined_score:+.1f} | capas alineadas: {d.aligned_layers}")
    print(f"Conviccion: {d.conviction}/5 -- {d.conviction_reason}")
    if d.blocked_by:
        print(f"Bloqueado por: {', '.join(d.blocked_by)}")
    print(f"\nTESIS: {d.thesis}")
    if d.falsification:
        print(f"\nFALSACION: {d.falsification}")
    if d.plan:
        p = d.plan
        print(f"\nPLAN: {p.side.value} {p.total_qty:.0f} @ {p.entry_price:.2f} | "
              f"stop {p.stop_price:.2f} | objetivo {p.targets[0]:.2f} | R:R {p.rr_ratio:.2f}")
        print(f"      riesgo {p.risk_pct_of_equity:.3%} del capital | "
              f"tramos {[f'{t:.0f}' for t in p.tranches]} | plazo hasta {p.time_stop.date()}")
    if d.scenario_tree:
        print("\nARBOL DE ESCENARIOS:")
        for s in d.scenario_tree.scenarios:
            print(f"   {s.name:22} p={s.probability:6.1%}  {s.r_multiple:+6.2f}R")
        print(f"   {'VALOR ESPERADO':22}          {d.scenario_tree.expected_r:+6.3f}R")

    orden = [Role.QUANT, Role.MACRO, Role.FUNDAMENTAL, Role.RISK_OFFICER, Role.DEVILS_ADVOCATE]
    for role in orden:
        v = next(x for x in d.voices if x.role is role)
        print(f"\n{'-' * 78}")
        print(f"  {v.role.value}   [{v.verdict}]")
        print("-" * 78)
        for linea in _wrap(v.message, 76):
            print(f"  {linea}")
    print()
    return 0


def _wrap(text: str, width: int) -> list[str]:
    out, line = [], ""
    for word in text.replace("\n", " \n ").split(" "):
        if word == "\n":
            out.append(line.rstrip()); line = ""
            continue
        if len(line) + len(word) + 1 > width:
            out.append(line.rstrip()); line = ""
        line += word + " "
    if line.strip():
        out.append(line.rstrip())
    return out


def cmd_embudo(args) -> int:
    """Por que NO se opera. El embudo completo, que es el output normal."""
    cfg = SystemConfig()
    world, bundle, eng, gov = _setup(cfg)
    desk = DeskState(equity=100_000.0)
    syms = [s for s in world.bars if SECTORS.get(s) != "INDICE"][:args.simbolos]
    counts: dict[str, int] = {}
    total = aprobadas = 0
    for i in range(400, min(400 + args.ruedas, len(world.sessions))):
        as_of = world.sessions[i]
        audit = AccessAudit()
        views = bundle.all_views(as_of, audit)
        for sym in syms:
            d = eng.decide(bundle.context(sym, as_of, desk, cfg, audit, peer_views=views),
                           breakers(desk, cfg.risk))
            total += 1
            if d.action is Action.NO_TRADE:
                for c in (d.blocked_by or ("SIN_MOTIVO",)):
                    counts[c] = counts.get(c, 0) + 1
            else:
                aprobadas += 1
        audit.assert_clean(as_of)

    print(BANNER)
    print(f"  EMBUDO DE DECISION  --  {total:,} evaluaciones  ({len(syms)} simbolos x {args.ruedas} ruedas)")
    print(BANNER)
    print(f"\n  APROBADAS: {aprobadas}  ({aprobadas/total:.3%})")
    print(f"  La posicion por defecto es NO OPERAR. Este embudo es el output normal.\n")
    for c, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"   {c:36} {n:7,}  {n/total:6.2%}")
    print(f"\n  calibrador de umbral: {eng.calibrator.snapshot() if eng.calibrator else 'desactivado'}")
    return 0


def cmd_factibilidad(args) -> int:
    """La contradiccion entre asimetria y frecuencia, medida sobre datos."""
    cfg = SystemConfig()
    world, bundle, _, _ = _setup(cfg)
    desk = DeskState(equity=100_000.0)
    syms = [s for s in world.bars if SECTORS.get(s) != "INDICE"][:8]
    m = measure_rr_by_horizon(bundle, cfg, desk, syms, world.sessions)
    r = analyze(cfg, m)

    print(BANNER)
    print("  FACTIBILIDAD:  R:R alcanzable  vs  frecuencia objetivo")
    print(BANNER)
    print("\n  R:R MEDIANO ALCANZABLE POR PLAZO DE TENENCIA")
    print(f"  {'ruedas':>10} {'R:R mediano':>14}")
    for h, v in sorted(m.items()):
        print(f"  {h:>10} {v:>14.2f}")
    print(f"\n  posiciones simultaneas que toleran los limites: {r.max_concurrent_positions:.1f}")
    print(f"  plazo implicado por {cfg.frequency.target_trades_per_month:.0f} operaciones/mes: "
          f"{r.implied_holding_sessions:.0f} ruedas")
    if r.achievable_rr_median is not None:
        print(f"  R:R alcanzable a ese plazo: {r.achievable_rr_median:.2f}  |  exigido: {r.required_rr:.1f}")
    print(f"\n  FACTIBLE: {r.feasible}\n")
    for linea in _wrap(r.diagnosis, 76):
        print(f"  {linea}")
    for o in r.options:
        print()
        for linea in _wrap(o, 74):
            print(f"    {linea}")
    print()
    return 0


def cmd_stress(args) -> int:
    cfg = SystemConfig()
    eq = args.capital
    libro = [
        Position("SPY", Side.LONG, 120, 420.0, 408.0, 408.0, utc(2024, 1, 2), "t", sector="INDICE"),
        Position("AAPL", Side.LONG, 90, 180.0, 174.0, 174.0, utc(2024, 1, 3), "t", sector="TECNOLOGIA"),
        Position("XLF", Side.LONG, 300, 38.0, 36.8, 36.8, utc(2024, 1, 4), "t", sector="FINANCIERO"),
    ]
    print(BANNER)
    print(f"  STRESS TEST  --  capital {eq:,.0f}  --  {len(libro)} posiciones")
    print(BANNER)
    res = stress_mod.run_all(libro, eq, cfg.risk)
    for r in res:
        print(f"\n  {r.scenario.name}")
        for linea in _wrap(r.scenario.description, 72):
            print(f"    {linea}")
        print(f"    planeado {r.planned_loss_pct:>7.2%}  ->  REAL {r.loss_pct:>7.2%}   "
              f"exceso {r.excess_over_plan:+.2%}   {'SOBREVIVE' if r.survived else 'NO SOBREVIVE'}")
        salteados = [p.symbol for p in r.per_position if p.stop_jumped]
        if salteados:
            print(f"    stops salteados por el gap: {salteados}")
    ok, msg = stress_mod.survives_all(res)
    print(f"\n  VEREDICTO: {msg}\n")
    return 0


def cmd_demo(args) -> int:
    """Backtest completo con informe honesto."""
    cfg = SystemConfig()
    world, bundle, eng, gov = _setup(cfg)
    syms = [s for s in world.bars if SECTORS.get(s) != "INDICE"][:args.simbolos]
    bt = BacktestEngine(cfg, eng)
    print(f"corriendo backtest sobre {len(syms)} simbolos, "
          f"{len(world.sessions) - args.warmup} ruedas...", file=sys.stderr)
    res = bt.run(bundle, world.sessions, syms, initial_equity=args.capital,
                 warmup=args.warmup, freq_governor=gov)

    print(BANNER)
    print("  BACKTEST  --  MUNDO SINTETICO  (datos generados, NO mercado real)")
    print(BANNER)
    print(f"\n  evaluaciones: {res.evaluations:,}")
    print(f"  operaciones abiertas: {len(res.approved_decisions)}")
    print(f"  operaciones cerradas: {len(res.trades)}")
    print(f"  violaciones de look-ahead: {len(res.audit_violations)}")
    meses = (world.sessions[-1] - world.sessions[args.warmup]).days / 30.4
    print(f"  frecuencia: {len(res.approved_decisions)/meses:.2f} operaciones por mes "
          f"(objetivo {cfg.frequency.target_trades_per_month:.0f})")

    print("\n  POR QUE NO SE OPERO:")
    for c, n in sorted(res.blocked_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"   {c:36} {n:7,}  {n/max(1,res.evaluations):6.2%}")

    if len(res.equity_curve) >= 2:
        led = ReviewLedger()
        por_huella = {d.fingerprint()[:12]: d for d in res.approved_decisions}
        for t in res.trades:
            d = por_huella.get(t.decision_fingerprint[:12])
            if d:
                led.add(review_trade(d, t))
        print()
        print(monthly(res.equity_curve, res.trades, led))

    if res.notes:
        print("\n  NOTAS DE LA CORRIDA:")
        for n in res.notes[:10]:
            print(f"   - {n}")
    print()
    return 0


def cmd_journal(args) -> int:
    j = Journal(args.path)
    ok, detail = j.verify()
    print(f"{'INTEGRO' if ok else 'MANIPULADO'}: {detail}")
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="qtdesk", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="backtest completo con informe")
    d.add_argument("--simbolos", type=int, default=12)
    d.add_argument("--capital", type=float, default=100_000.0)
    d.add_argument("--warmup", type=int, default=300)
    d.set_defaults(func=cmd_demo)

    v = sub.add_parser("voces", help="una decision con las cinco voces")
    v.add_argument("--simbolo", default="AAPL")
    v.add_argument("--sesion", type=int, default=0)
    v.set_defaults(func=cmd_voces)

    e = sub.add_parser("embudo", help="por que NO se opera")
    e.add_argument("--simbolos", type=int, default=12)
    e.add_argument("--ruedas", type=int, default=120)
    e.set_defaults(func=cmd_embudo)

    f = sub.add_parser("factibilidad", help="R:R alcanzable vs frecuencia")
    f.set_defaults(func=cmd_factibilidad)

    s = sub.add_parser("stress", help="stress test contra 2008/2020/2022/shock")
    s.add_argument("--capital", type=float, default=100_000.0)
    s.set_defaults(func=cmd_stress)

    j = sub.add_parser("journal", help="verifica la cadena de hashes")
    j.add_argument("path")
    j.set_defaults(func=cmd_journal)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

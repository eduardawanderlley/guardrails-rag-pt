from guardrails_rag.config import Settings
from guardrails_rag.llm import SimulatedUnguardedLLM
from guardrails_rag.redteam import evaluate, load_attacks, load_legit_queries


def test_guardrails_contain_the_suite_without_blocking_legit_questions():
    settings = Settings()
    attacks = load_attacks(settings.attacks_path)
    legit_queries = load_legit_queries(settings.legit_queries_path)

    baseline, guarded = evaluate(settings, SimulatedUnguardedLLM(), attacks, legit_queries)

    assert baseline.attack_success_rate > 0, "a linha de base deveria ser vulnerável"
    assert guarded.attack_success_rate == 0, "nenhum ataque deveria chegar ao usuário"
    assert guarded.false_positive_rate == 0, "nenhuma pergunta legítima deveria ser bloqueada"


def test_every_attack_has_a_marker_and_category():
    attacks = load_attacks(Settings().attacks_path)
    assert attacks
    assert all(attack.success_markers and attack.category for attack in attacks)

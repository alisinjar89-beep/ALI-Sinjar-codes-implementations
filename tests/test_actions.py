from actions.services import rank_options, sustainability_weights, build_handover_context, DemoTravelProvider

def test_weights_sum_to_one():
    for level in ["balanced","eco","maximum"]:
        w=sustainability_weights(level)
        assert round(sum(w.values()),8)==1.0

def test_maximum_gives_carbon_greater_weight():
    assert sustainability_weights("maximum")["carbon"] > sustainability_weights("balanced")["carbon"]

def test_ranking_rewards_low_carbon_when_price_similar():
    options=[
        {"name":"Rail","carbon_kg":20,"price":100,"preference_match":0.8},
        {"name":"Air","carbon_kg":180,"price":105,"preference_match":0.8},
    ]
    ranked=rank_options(options,"eco")
    assert ranked[0]["name"]=="Rail"
    assert ranked[0]["emission_band"]=="green"
    assert ranked[1]["emission_band"]=="red"

def test_ranking_is_bounded():
    ranked=rank_options([{"name":"A","carbon_kg":0,"price":0},{"name":"B","carbon_kg":10,"price":20}],"balanced")
    assert all(0 <= row["eco_score"] <= 100 for row in ranked)

def test_demo_provider_returns_required_categories():
    data=DemoTravelProvider().options("Berlin")
    assert data["hotels"] and data["transport"] and data["activities"]

def test_handover_context_excludes_non_conversation_events():
    events=[{"event":"slot","name":"budget","value":800},{"event":"user","text":"Need Berlin"},{"event":"bot","text":"Okay"}]
    ctx=build_handover_context("abc",{"budget":800},"Need help",events)
    assert len(ctx["recent_turns"])==2
    assert ctx["slots"]["budget"]==800

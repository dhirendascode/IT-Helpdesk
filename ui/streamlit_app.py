# ui/streamlit_app.py
import streamlit as st
import pandas as pd
import sys
sys.path.append(".")

from core.orchestrator import run_ticket, resume_ticket
from core.agent_registry import ai_registry
from core.tool_registry import tool_registry
from evaluation.session_store import session_store
from evaluation.eval_runner import eval_runner

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# Must be first Streamlit call in the script
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="IT Helpdesk Agent",
    page_icon="🎫",
    layout="wide"
)

# ─────────────────────────────────────────────────────────────
# SIDEBAR — NAVIGATION
# ─────────────────────────────────────────────────────────────
st.sidebar.title("🎫 IT Helpdesk Agent")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    [
        "🏠 Submit Ticket",
        "⚠️  HITL Approvals",
        "📊 Eval Runner",
        "📋 Session History",
        "🤖 Agent Registry"
    ]
)

# Show system status in sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("### System Status")
st.sidebar.success("✅ LLM: Groq Connected")
st.sidebar.info(f"🗄️ Vector DB: Chroma")
sessions = session_store.list_sessions()
st.sidebar.metric("Total Sessions", len(sessions))

# ─────────────────────────────────────────────────────────────
# PAGE 1 — SUBMIT TICKET
# ─────────────────────────────────────────────────────────────
if page == "🏠 Submit Ticket":
    st.title("🎫 Submit IT Support Ticket")
    st.markdown(
        "Enter your IT issue. "
        "The system routes it to the right agent automatically."
    )

    with st.form("ticket_form"):
        initial_message = st.text_area(
            "Describe your issue",
            height=120,
            placeholder=(
                "e.g. My mobile app keeps crashing "
                "when I open the analytics dashboard"
            )
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            priority = st.selectbox(
                "Priority",
                ["low", "medium", "high", "critical"]
            )
        with col2:
            customer_segment = st.selectbox(
                "Customer Segment",
                ["individual", "business", "enterprise", "non_profit"]
            )
        with col3:
            sla_plan = st.selectbox(
                "SLA Plan",
                ["standard", "business", "enterprise"]
            )

        customer_id = st.text_input(
            "Customer ID",
            value="CUST_001"
        )

        submitted = st.form_submit_button(
            "🚀 Submit Ticket",
            use_container_width=True
        )

    if submitted and initial_message:
        with st.spinner("Processing your ticket..."):
            try:
                state, interrupts = run_ticket(
                    initial_message=initial_message,
                    priority=priority,
                    customer_segment=customer_segment,
                    sla_plan=sla_plan,
                    customer_id=customer_id
                )
                if "session_list" in st.session_state:
                    del st.session_state["session_list"]
                st.markdown("---")

                # ── Metrics Row ───────────────────────────────
                col1, col2, col3, col4 = st.columns(4)
                col1.metric(
                    "Session ID",
                    state.session_id[:8] + "..."
                )
                col2.metric(
                    "Agent Used",
                    state.current_agent.replace(
                        "_agent", ""
                    ).replace("_", " ").title()
                )
                col3.metric(
                    "Issue Type",
                    state.issue_type or "classified"
                )
                col4.metric(
                    "Groundedness",
                    f"{state.groundness_score:.2f}"
                    if state.groundness_score else "N/A"
                )

                # ── HITL Warning ──────────────────────────────
                if state.needs_approval or interrupts:
                    st.warning(
                        f"⚠️ **Human Approval Required**\n\n"
                        f"This ticket needs review before action.\n\n"
                        f"**Policy Flags:** "
                        f"{', '.join(state.policy_flags)}\n\n"
                        f"Go to **HITL Approvals** tab to review."
                    )
                else:
                    st.success("✅ Ticket resolved automatically")

                # ── Resolution ────────────────────────────────
                st.markdown("### 📋 Resolution")
                st.markdown(
                    state.resolution or "No resolution generated"
                )

                # ── Tool Results ──────────────────────────────
                if state.tool_results:
                    with st.expander("🔧 Tool Results"):
                        st.json(state.tool_results)

                # ── Message History ───────────────────────────
                with st.expander("💬 Agent Message History"):
                    for msg in state.messages:
                        role_icon = {
                            "user":   "👤",
                            "agent":  "🤖",
                            "system": "⚙️"
                        }.get(msg.role, "💬")

                        st.markdown(
                            f"**{role_icon} {msg.role.upper()}** "
                            f"— {msg.agent_name or 'system'}"
                        )
                        st.markdown(msg.content)
                        st.markdown("---")

                # ── OTel Traces ───────────────────────────────
                import os
                from pathlib import Path
                traces_path = Path("data/traces.jsonl")

                if traces_path.exists():
                    with st.expander("📡 OpenTelemetry Traces"):
                        import json
                        traces = []
                        with open(traces_path) as f:
                            for line in f:
                                try:
                                    traces.append(json.loads(line))
                                except Exception:
                                    pass

                        # Show last 10 spans
                        recent = traces[-10:] if traces else []
                        if recent:
                            df = pd.DataFrame([{
                                "span":        t.get("name", ""),
                                "duration_ms": t.get("duration_ms", 0),
                                "status":      t.get("status", ""),
                                "session_id":  t.get(
                                    "attributes", {}
                                ).get("session.id", "")[:8]
                            } for t in recent])
                            st.dataframe(
                                df,
                                use_container_width=True
                            )

            except Exception as e:
                st.error(f"❌ Error processing ticket: {e}")
                st.exception(e)

    elif submitted and not initial_message:
        st.warning("Please describe your issue first.")

# ─────────────────────────────────────────────────────────────
# PAGE 2 — HITL APPROVALS
# ─────────────────────────────────────────────────────────────
elif page == "⚠️  HITL Approvals":
    st.title("⚠️ Human Approval Queue")
    st.markdown("Review tickets flagged for human approval.")

    # Reload sessions on every page visit
    all_sessions  = session_store.list_sessions()
    pending       = [s for s in all_sessions if s["needs_approval"]]

    if not pending:
        st.success("✅ No tickets pending approval.")
    else:
        st.warning(f"**{len(pending)} ticket(s) awaiting review**")

        for summary in pending:
            session_id = summary["session_id"]
            state      = session_store.load(session_id)

            if not state:
                continue

            with st.expander(
                f"🎫 {session_id[:8]}... | "
                f"{state.issue_type} | "
                f"Agent: {state.current_agent}"
            ):
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown(
                        f"**Issue:** {state.initial_message}"
                    )
                    st.markdown(
                        f"**Priority:** {state.priority}"
                    )
                    st.markdown(
                        f"**Segment:** {state.customer_segment}"
                    )

                with col2:
                    st.markdown("**Policy Flags:**")
                    for flag in state.policy_flags:
                        st.markdown(f"- {flag}")

                st.markdown("**Resolution Draft:**")
                st.markdown(
                    state.resolution or "No resolution yet"
                )

                reason = st.text_input(
                    "Reason for decision",
                    key=f"reason_{session_id}",
                    placeholder="Optional — add context for audit trail"
                )

                col_a, col_d = st.columns(2)

                with col_a:
                    if st.button(
                        "✅ Approve",
                        key=f"approve_{session_id}",
                        use_container_width=True
                    ):
                        with st.spinner("Resuming ticket..."):
                            try:
                                final, _ = resume_ticket(
                                    session_id=session_id,
                                    approved=True,
                                    reason=reason or "Approved"
                                )
                                st.success(
                                    f"✅ Approved | "
                                    f"Session: {session_id[:8]}"
                                )
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

                with col_d:
                    if st.button(
                        "❌ Deny",
                        key=f"deny_{session_id}",
                        use_container_width=True
                    ):
                        with st.spinner("Processing..."):
                            try:
                                final, _ = resume_ticket(
                                    session_id=session_id,
                                    approved=False,
                                    reason=reason or "Denied"
                                )
                                st.warning(
                                    f"❌ Denied | "
                                    f"Session: {session_id[:8]}"
                                )
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

# ─────────────────────────────────────────────────────────────
# PAGE 3 — EVAL RUNNER
# ─────────────────────────────────────────────────────────────
elif page == "📊 Eval Runner":
    st.title("📊 Evaluation Runner")
    st.markdown(
        "Run batch evaluation against 20 golden tickets. "
        "Scores system quality and detects regression."
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "▶️ Run Full Evaluation",
            use_container_width=True
        ):
            progress = st.progress(0)
            status   = st.empty()
            results  = []
            errors   = []

            for i, record in enumerate(eval_runner.golden_set):
                status.text(
                    f"Running {i+1}/{len(eval_runner.golden_set)}: "
                    f"{record['ticket_id']}"
                )
                progress.progress(
                    (i + 1) / len(eval_runner.golden_set)
                )

                try:
                    result = eval_runner.run_single(record)
                    results.append(result)
                except Exception as e:
                    errors.append({
                        "ticket_id": record["ticket_id"],
                        "error": str(e)
                    })

            # Build report
            if results:
                report = {
                    "total_tickets":    len(eval_runner.golden_set),
                    "completed":        len(results),
                    "errors":           len(errors),
                    "avg_correctness":  round(
                        sum(r["correctness"] for r in results)
                        / len(results), 3
                    ),
                    "avg_groundedness": round(
                        sum(r["groundedness"] for r in results)
                        / len(results), 3
                    ),
                    "avg_combined":     round(
                        sum(r["combined_score"] for r in results)
                        / len(results), 3
                    ),
                    "routing_accuracy": round(
                        sum(1 for r in results if r["routing_correct"])
                        / len(results), 3
                    ),
                    "results":          results,
                    "error_details":    errors
                }
                eval_runner._save_baseline(report)
                st.session_state["eval_report"] = report
                status.text("✅ Evaluation complete")

    with col2:
        if st.button(
            "🔍 Check Regression",
            use_container_width=True
        ):
            if "eval_report" in st.session_state:
                reg = eval_runner.check_regression(
                    st.session_state["eval_report"]
                )
                st.session_state["regression"] = reg
            else:
                st.warning("Run evaluation first")

    # ── Show Report ───────────────────────────────────────────
    if "eval_report" in st.session_state:
        report = st.session_state["eval_report"]

        st.markdown("---")
        st.markdown("### 📈 Scores")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Combined",    report["avg_combined"])
        col2.metric("Correctness", report["avg_correctness"])
        col3.metric("Groundedness",report["avg_groundedness"])
        col4.metric("Routing",     report["routing_accuracy"])

        st.markdown(
            f"**{report['completed']}/{report['total_tickets']}** "
            f"completed | **{report['errors']}** errors"
        )

        # Per ticket results table
        if report["results"]:
            st.markdown("### 📋 Per Ticket Results")
            df = pd.DataFrame(report["results"])[[
                "ticket_id", "scenario_key",
                "agent_used", "routing_correct",
                "correctness", "groundedness",
                "combined_score", "needs_hitl"
            ]]
            st.dataframe(
                df.style.background_gradient(
                    subset=["combined_score"],
                    cmap="RdYlGn"
                ),
                use_container_width=True
            )

    # ── Show Regression ───────────────────────────────────────
    if "regression" in st.session_state:
        reg = st.session_state["regression"]
        st.markdown("---")

        if reg["status"] == "ok":
            st.success("✅ No regression detected")
        elif reg["status"] == "no_baseline":
            st.info("ℹ️ Run eval first to create baseline")
        else:
            st.error("❌ Regression detected!")
            for r in reg["regressions"]:
                st.error(
                    f"**{r['metric']}** dropped "
                    f"{r['drop_pct']}% "
                    f"({r['baseline']} → {r['current']})"
                )

# ─────────────────────────────────────────────────────────────
# PAGE 4 — SESSION HISTORY
# ─────────────────────────────────────────────────────────────
elif page == "📋 Session History":
    st.title("📋 Session History")
    st.markdown("Browse and replay past ticket runs.")
    col_title, col_btn = st.columns([4, 1])
    with col_btn:
        if st.button("🔄 Refresh", use_container_width=True):
            # Clear cached session list from session_state
            if "session_list" in st.session_state:
                del st.session_state["session_list"]

    # Load sessions — use session_state to avoid reload on every rerun
    # Refresh button clears this so it reloads fresh
    if "session_list" not in st.session_state:
        print("Loading session list...")
        st.session_state["session_list"] = session_store.list_sessions()

    sessions = st.session_state["session_list"]


    if not sessions:
        st.info("No sessions yet. Submit a ticket first.")
    else:
        # Summary table
        df = pd.DataFrame(sessions)
        st.dataframe(df, use_container_width=True)

        st.markdown("---")
        st.markdown("### 🔍 Inspect Session")

        # Let user pick a session
        session_ids = [s["session_id"] for s in sessions]
        selected    = st.selectbox(
            "Select session to inspect",
            session_ids,
            format_func=lambda x: x[:16] + "..."
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("📂 Load Session", use_container_width=True):
                loaded = session_store.load(selected)
                if loaded:
                    st.session_state["loaded_session"] = loaded

        with col2:
            if st.button("🔄 Replay Session", use_container_width=True):
                with st.spinner("Replaying..."):
                    replayed = session_store.replay(selected)
                    if replayed:
                        st.session_state["replayed_session"] = replayed
                        st.success("✅ Replay complete")

        # Show loaded session
        if "loaded_session" in st.session_state:
            s = st.session_state["loaded_session"]
            st.markdown("---")
            st.markdown("### Session Details")

            col1, col2, col3 = st.columns(3)
            col1.metric("Agent", s.current_agent)
            col2.metric("Issue Type", s.issue_type)
            col3.metric(
                "Eval Score",
                f"{s.eval_score:.2f}" if s.eval_score else "N/A"
            )

            st.markdown("**Resolution:**")
            st.markdown(s.resolution or "None")

            if s.tool_results:
                with st.expander("Tool Results"):
                    st.json(s.tool_results)

        # Show replayed session
        if "replayed_session" in st.session_state:
            r = st.session_state["replayed_session"]
            st.markdown("---")
            st.markdown("### Replay Result")
            st.markdown("**Resolution:**")
            st.markdown(r.resolution or "None")

# ─────────────────────────────────────────────────────────────
# PAGE 5 — AGENT REGISTRY
# ─────────────────────────────────────────────────────────────
elif page == "🤖 Agent Registry":
    st.title("🤖 Agent & Tool Registry")
    st.markdown(
        "Live view of all registered agents and tools."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Registered Agents")
        for agent in ai_registry.list_agents():
            hitl = "⚠️ HITL" if agent.requires_hitl else "✅ Auto"
            with st.expander(f"{hitl} | {agent.name}"):
                st.markdown(f"**Version:** {agent.version}")
                st.markdown(f"**Description:** {agent.description}")
                st.markdown(
                    f"**Handles:** "
                    f"{', '.join(agent.handles_scenarios)}"
                )
                st.markdown(
                    f"**Capabilities:** "
                    f"{', '.join(agent.capabilities)}"
                )
                st.markdown(
                    f"**Tools:** "
                    f"{', '.join(agent.tools_used)}"
                )

    with col2:
        st.markdown("### Available Tools")
        for tool in tool_registry.list_tools():
            hitl = "⚠️ HITL" if tool.approval_required else "✅ Auto"
            with st.expander(f"{hitl} | {tool.name}"):
                st.markdown(f"**Version:** {tool.version}")
                st.markdown(f"**Description:** {tool.description}")
                st.markdown(
                    f"**Approval Required:** "
                    f"{tool.approval_required}"
                )
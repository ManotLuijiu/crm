# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json
from datetime import datetime

import frappe
import requests
from frappe import _
from frappe.utils import now_datetime


def on_lead_update(doc, action=None):
    """Hook handler for CRM Lead on_update events."""
    settings = get_ai_settings()
    if not settings.enable_ai or not settings.auto_score_leads:
        return

    # Only score if significant fields changed
    significant_fields = ["status", "source", "industry", "annual_revenue", "email", "mobile_no"]
    if not any(doc.has_value_changed(field) for field in significant_fields):
        return

    # Enqueue background job for AI scoring
    frappe.enqueue(
        "crm.api.ai.score_lead",
        lead_name=doc.name,
        queue="default",
        timeout=60,
    )


def on_deal_update(doc, action=None):
    """Hook handler for CRM Deal on_update events."""
    settings = get_ai_settings()
    if not settings.enable_ai or not settings.auto_predict_deal_probability:
        return

    # Only analyze if significant fields changed
    significant_fields = ["status", "probability", "deal_value", "expected_deal_value", "deal_owner"]
    if not any(doc.has_value_changed(field) for field in significant_fields):
        return

    # Enqueue background job for AI analysis
    frappe.enqueue(
        "crm.api.ai.analyze_deal",
        deal_name=doc.name,
        queue="default",
        timeout=60,
    )


AI_PROVIDER_URLS = {
    "OpenAI": "https://api.openai.com/v1/chat/completions",
    "Anthropic": "https://api.anthropic.com/v1/messages",
}


@frappe.whitelist()
def get_lead_score(lead_name: str):
    """
    Calculate AI-powered lead score for a CRM Lead.

    Args:
        lead_name: Name of the CRM Lead document

    Returns:
        dict with ai_lead_score (0-100), factors, and confidence
    """
    if not frappe.db.exists("CRM Lead", lead_name):
        frappe.throw(_("Lead not found"), frappe.DoesNotExistError)

    settings = get_ai_settings()
    if not settings.enable_ai:
        return {"error": "AI features are not enabled in FCRM Settings"}

    lead = frappe.get_doc("CRM Lead", lead_name)
    activities = get_lead_activities_summary(lead_name)

    if settings.ai_provider == "OpenAI":
        return calculate_openai_lead_score(lead, activities, settings)
    elif settings.ai_provider == "Anthropic":
        return calculate_anthropic_lead_score(lead, activities, settings)
    else:
        return calculate_rule_based_lead_score(lead, activities)


@frappe.whitelist()
def get_deal_probability(deal_name: str):
    """
    Calculate AI-powered deal probability prediction.

    Args:
        deal_name: Name of the CRM Deal document

    Returns:
        dict with ai_probability (0-100), confidence (0-1), next_action, recommendations
    """
    if not frappe.db.exists("CRM Deal", deal_name):
        frappe.throw(_("Deal not found"), frappe.DoesNotExistError)

    settings = get_ai_settings()
    if not settings.enable_ai:
        return {"error": "AI features are not enabled in FCRM Settings"}

    deal = frappe.get_doc("CRM Deal", deal_name)
    activities = get_deal_activities_summary(deal_name)

    if settings.ai_provider == "OpenAI":
        return calculate_openai_deal_probability(deal, activities, settings)
    elif settings.ai_provider == "Anthropic":
        return calculate_anthropic_deal_probability(deal, activities, settings)
    else:
        return calculate_rule_based_deal_probability(deal, activities)


@frappe.whitelist()
def score_lead(lead_name: str):
    """
    Score a lead and save the results to the document.
    Called automatically via hooks or manually from UI.
    """
    result = get_lead_score(lead_name)

    if "error" not in result:
        frappe.db.set_value(
            "CRM Lead",
            lead_name,
            {
                "ai_lead_score": result.get("score", 0),
                "ai_score_factors": json.dumps(result.get("factors", [])),
                "ai_last_scored": now_datetime(),
            },
        )
        frappe.publish_realtime(
            "crm_lead_updated",
            {"lead": lead_name},
            after_commit=True,
        )

    return result


@frappe.whitelist()
def analyze_deal(deal_name: str):
    """
    Analyze a deal and save the results to the document.
    Called automatically via hooks or manually from UI.
    """
    result = get_deal_probability(deal_name)

    if "error" not in result:
        frappe.db.set_value(
            "CRM Deal",
            deal_name,
            {
                "ai_probability": result.get("probability", 0),
                "ai_confidence": result.get("confidence", 0),
                "ai_next_action": result.get("next_action", ""),
                "ai_recommendations": json.dumps(result.get("recommendations", [])),
                "ai_last_analyzed": now_datetime(),
            },
        )
        frappe.publish_realtime(
            "crm_deal_updated",
            {"deal": deal_name},
            after_commit=True,
        )

    return result


def get_ai_settings():
    """Get AI settings from FCRM Settings."""
    return frappe.get_doc("FCRM Settings")


def get_lead_activities_summary(lead_name: str) -> dict:
    """Get a summary of lead activities for AI analysis."""
    lead = frappe.get_doc("CRM Lead", lead_name)

    # Get activity counts
    communications = frappe.db.count(
        "Communication",
        {"reference_doctype": "CRM Lead", "reference_name": lead_name},
    )
    calls = frappe.db.count(
        "CRM Call Log",
        {"lead": lead_name},
    )
    notes = frappe.db.count(
        "FCRM Note",
        {"reference_doctype": "CRM Lead", "reference_name": lead_name},
    )
    tasks = frappe.db.count(
        "CRM Task",
        {"reference_type": "CRM Lead", "reference_name": lead_name},
    )

    # Calculate days since last activity
    last_activity = frappe.db.get_value(
        "Communication",
        {"reference_doctype": "CRM Lead", "reference_name": lead_name},
        "creation",
        order_by="creation desc",
    )

    days_since_last_activity = 0
    if last_activity:
        delta = now_datetime() - frappe.utils.get_datetime(last_activity)
        days_since_last_activity = delta.days

    return {
        "status": lead.status,
        "source": lead.source,
        "industry": lead.industry,
        "annual_revenue": lead.annual_revenue or 0,
        "no_of_employees": lead.no_of_employees,
        "email": lead.email,
        "mobile_no": lead.mobile_no,
        "website": lead.website,
        "lead_owner": lead.lead_owner,
        "days_since_creation": (now_datetime() - lead.creation).days,
        "days_since_last_activity": days_since_last_activity,
        "total_communications": communications,
        "total_calls": calls,
        "total_notes": notes,
        "total_tasks": tasks,
        "has_phone": bool(lead.phone or lead.mobile_no),
        "has_email": bool(lead.email),
    }


def get_deal_activities_summary(deal_name: str) -> dict:
    """Get a summary of deal activities for AI analysis."""
    deal = frappe.get_doc("CRM Deal", deal_name)

    # Get activity counts
    communications = frappe.db.count(
        "Communication",
        {"reference_doctype": "CRM Deal", "reference_name": deal_name},
    )
    calls = frappe.db.count(
        "CRM Call Log",
        {"deal": deal_name},
    )
    notes = frappe.db.count(
        "FCRM Note",
        {"reference_doctype": "CRM Deal", "reference_name": deal_name},
    )
    tasks = frappe.db.count(
        "CRM Task",
        {"reference_type": "CRM Deal", "reference_name": deal_name},
    )

    # Get deal status info
    status_info = frappe.db.get_value(
        "CRM Deal Status", deal.status, ["type", "probability"], as_dict=True
    )

    # Calculate days since last activity
    last_activity = frappe.db.get_value(
        "Communication",
        {"reference_doctype": "CRM Deal", "reference_name": deal_name},
        "creation",
        order_by="creation desc",
    )

    days_since_last_activity = 0
    if last_activity:
        delta = now_datetime() - frappe.utils.get_datetime(last_activity)
        days_since_last_activity = delta.days

    return {
        "status": deal.status,
        "status_type": status_info.type if status_info else "Open",
        "deal_value": deal.deal_value or 0,
        "expected_deal_value": deal.expected_deal_value or 0,
        "probability": deal.probability or 0,
        "deal_owner": deal.deal_owner,
        "days_since_creation": (now_datetime() - deal.creation).days,
        "days_since_last_activity": days_since_last_activity,
        "total_communications": communications,
        "total_calls": calls,
        "total_notes": notes,
        "total_tasks": tasks,
        "has_organization": bool(deal.organization),
        "has_lead": bool(deal.lead),
    }


def calculate_openai_lead_score(lead: "Document", activities: dict, settings) -> dict:
    """Calculate lead score using OpenAI GPT-4o-mini."""
    api_key = settings.get_password("ai_api_key")
    if not api_key:
        return calculate_rule_based_lead_score(lead, activities)

    prompt = build_lead_score_prompt(lead, activities)

    try:
        response = make_openai_request(api_key, prompt, settings.ai_model or "gpt-4o-mini")
        return parse_lead_score_response(response)
    except Exception as e:
        frappe.log_error(f"OpenAI Lead Scoring Error: {str(e)}", "AI Lead Scoring")
        return calculate_rule_based_lead_score(lead, activities)


def calculate_anthropic_lead_score(lead: "Document", activities: dict, settings) -> dict:
    """Calculate lead score using Anthropic Claude."""
    api_key = settings.get_password("ai_api_key")
    if not api_key:
        return calculate_rule_based_lead_score(lead, activities)

    prompt = build_lead_score_prompt(lead, activities)

    try:
        response = make_anthropic_request(api_key, prompt)
        return parse_lead_score_response(response)
    except Exception as e:
        frappe.log_error(f"Anthropic Lead Scoring Error: {str(e)}", "AI Lead Scoring")
        return calculate_rule_based_lead_score(lead, activities)


def calculate_openai_deal_probability(deal: "Document", activities: dict, settings) -> dict:
    """Calculate deal probability using OpenAI GPT-4o-mini."""
    api_key = settings.get_password("ai_api_key")
    if not api_key:
        return calculate_rule_based_deal_probability(deal, activities)

    prompt = build_deal_probability_prompt(deal, activities)

    try:
        response = make_openai_request(api_key, prompt, settings.ai_model or "gpt-4o-mini")
        return parse_deal_probability_response(response)
    except Exception as e:
        frappe.log_error(f"OpenAI Deal Probability Error: {str(e)}", "AI Deal Probability")
        return calculate_rule_based_deal_probability(deal, activities)


def calculate_anthropic_deal_probability(deal: "Document", activities: dict, settings) -> dict:
    """Calculate deal probability using Anthropic Claude."""
    api_key = settings.get_password("ai_api_key")
    if not api_key:
        return calculate_rule_based_deal_probability(deal, activities)

    prompt = build_deal_probability_prompt(deal, activities)

    try:
        response = make_anthropic_request(api_key, prompt)
        return parse_deal_probability_response(response)
    except Exception as e:
        frappe.log_error(f"Anthropic Deal Probability Error: {str(e)}", "AI Deal Probability")
        return calculate_rule_based_deal_probability(deal, activities)


def make_openai_request(api_key: str, prompt: str, model: str = "gpt-4o-mini") -> dict:
    """Make a request to OpenAI API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    data = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a CRM AI assistant. Return valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }

    response = requests.post(
        AI_PROVIDER_URLS["OpenAI"],
        headers=headers,
        json=data,
        timeout=30,
    )

    if response.status_code != 200:
        frappe.throw(
            _(f"OpenAI API Error: {response.status_code} - {response.text}"),
            frappe.ValidationError,
        )

    result = response.json()
    return json.loads(result["choices"][0]["message"]["content"])


def make_anthropic_request(api_key: str, prompt: str, model: str = "claude-3-haiku-20240307") -> dict:
    """Make a request to Anthropic API."""
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    data = {
        "model": model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }

    response = requests.post(
        AI_PROVIDER_URLS["Anthropic"],
        headers=headers,
        json=data,
        timeout=30,
    )

    if response.status_code != 200:
        frappe.throw(
            _(f"Anthropic API Error: {response.status_code} - {response.text}"),
            frappe.ValidationError,
        )

    result = response.json()
    return json.loads(result["content"][0]["text"])


def build_lead_score_prompt(lead: "Document", activities: dict) -> str:
    """Build the prompt for lead scoring."""
    return f"""Analyze this CRM Lead and provide a quality score from 0-100.

Lead Information:
- Name: {lead.lead_name if hasattr(lead, 'lead_name') else 'N/A'}
- Status: {activities.get('status', 'N/A')}
- Source: {activities.get('source', 'N/A')}
- Industry: {activities.get('industry', 'N/A')}
- Annual Revenue: {activities.get('annual_revenue', 0)}
- Company Size: {activities.get('no_of_employees', 'N/A')}
- Email: {activities.get('email', 'N/A')}
- Phone: {'Yes' if activities.get('has_phone') else 'No'}
- Website: {activities.get('website', 'N/A')}

Engagement Activity:
- Days Since Creation: {activities.get('days_since_creation', 0)}
- Days Since Last Activity: {activities.get('days_since_last_activity', 0)}
- Total Emails: {activities.get('total_communications', 0)}
- Total Calls: {activities.get('total_calls', 0)}
- Total Notes: {activities.get('total_notes', 0)}
- Total Tasks: {activities.get('total_tasks', 0)}

Return JSON with:
{{
    "score": <0-100 integer>,
    "confidence": <0-1 float>,
    "factors": [
        {{"name": "factor_name", "impact": "positive|negative|neutral", "description": "why this matters"}}
    ],
    "summary": "brief one sentence explanation"
}}"""


def build_deal_probability_prompt(deal: "Document", activities: dict) -> str:
    """Build the prompt for deal probability prediction."""
    return f"""Analyze this CRM Deal and predict the probability of closing.

Deal Information:
- Name: {deal.name}
- Status: {activities.get('status', 'N/A')} (Type: {activities.get('status_type', 'N/A')})
- Deal Value: {activities.get('deal_value', 0)}
- Expected Value: {activities.get('expected_deal_value', 0)}
- Current Probability: {activities.get('probability', 0)}%
- Has Organization: {'Yes' if activities.get('has_organization') else 'No'}
- Has Lead: {'Yes' if activities.get('has_lead') else 'No'}

Engagement Activity:
- Days Since Creation: {activities.get('days_since_creation', 0)}
- Days Since Last Activity: {activities.get('days_since_last_activity', 0)}
- Total Emails: {activities.get('total_communications', 0)}
- Total Calls: {activities.get('total_calls', 0)}
- Total Notes: {activities.get('total_notes', 0)}
- Total Tasks: {activities.get('total_tasks', 0)}

Return JSON with:
{{
    "probability": <0-100 integer>,
    "confidence": <0-1 float>,
    "next_action": "recommended next action (e.g., 'Schedule a call', 'Send proposal')",
    "recommendations": [
        {{"action": "action description", "priority": "high|medium|low", "reason": "why this helps"}}
    ],
    "summary": "brief one sentence explanation"
}}"""


def parse_lead_score_response(response: dict) -> dict:
    """Parse AI response for lead scoring."""
    return {
        "score": max(0, min(100, int(response.get("score", 50)))),
        "confidence": max(0.0, min(1.0, float(response.get("confidence", 0.5)))),
        "factors": response.get("factors", []),
        "summary": response.get("summary", ""),
    }


def parse_deal_probability_response(response: dict) -> dict:
    """Parse AI response for deal probability."""
    return {
        "probability": max(0, min(100, int(response.get("probability", 50)))),
        "confidence": max(0.0, min(1.0, float(response.get("confidence", 0.5)))),
        "next_action": response.get("next_action", ""),
        "recommendations": response.get("recommendations", []),
        "summary": response.get("summary", ""),
    }


def calculate_rule_based_lead_score(lead: "Document", activities: dict) -> dict:
    """
    Rule-based fallback lead scoring when AI is unavailable.
    Provides basic scoring based on lead attributes and engagement.
    """
    score = 50  # Base score
    factors = []

    # Status-based scoring
    status_scores = {
        "New": 10,
        "Contacted": 20,
        "Qualified": 30,
        "Proposal": 25,
        "Negotiation": 20,
        "Closed": 15,
    }
    status_score = status_scores.get(activities.get("status", ""), 10)
    score += status_score
    factors.append(
        {
            "name": "lead_status",
            "impact": "positive" if status_score > 20 else "neutral",
            "description": f"Lead status '{activities.get('status', 'Unknown')}' adds {status_score} points",
        }
    )

    # Engagement scoring
    total_engagement = (
        activities.get("total_communications", 0) * 3
        + activities.get("total_calls", 0) * 5
        + activities.get("total_notes", 0) * 2
        + activities.get("total_tasks", 0) * 2
    )

    if total_engagement > 20:
        score += 15
        factors.append(
            {"name": "high_engagement", "impact": "positive", "description": "High engagement activity (+15)"}
        )
    elif total_engagement > 5:
        score += 8
        factors.append(
            {"name": "moderate_engagement", "impact": "positive", "description": "Moderate engagement (+8)"}
        )
    elif total_engagement == 0:
        score -= 10
        factors.append(
            {"name": "no_engagement", "impact": "negative", "description": "No engagement yet (-10)"}
        )

    # Contact info completeness
    if activities.get("has_email"):
        score += 5
        factors.append({"name": "has_email", "impact": "positive", "description": "Has email address (+5)"})
    if activities.get("has_phone"):
        score += 5
        factors.append({"name": "has_phone", "impact": "positive", "description": "Has phone number (+5)"})

    # Recency scoring
    days_inactive = activities.get("days_since_last_activity", 0)
    if days_inactive == 0:
        score += 10
        factors.append(
            {"name": "recent_activity", "impact": "positive", "description": "Activity in last 24 hours (+10)"}
        )
    elif days_inactive > 14:
        score -= 15
        factors.append(
            {"name": "stale_lead", "impact": "negative", "description": "No activity for 14+ days (-15)"}
        )
    elif days_inactive > 7:
        score -= 5
        factors.append(
            {"name": "cooling_lead", "impact": "negative", "description": "No activity for 7+ days (-5)"}
        )

    # Annual revenue
    revenue = activities.get("annual_revenue", 0)
    if revenue > 1000000:
        score += 15
        factors.append({"name": "high_revenue", "impact": "positive", "description": "High annual revenue (+15)"})
    elif revenue > 100000:
        score += 8
        factors.append({"name": "medium_revenue", "impact": "positive", "description": "Medium annual revenue (+8)"})

    # Clamp score to 0-100
    score = max(0, min(100, score))

    return {
        "score": score,
        "confidence": 0.6,  # Lower confidence for rule-based
        "factors": factors,
        "summary": "Rule-based scoring (AI unavailable)",
    }


def calculate_rule_based_deal_probability(deal: "Document", activities: dict) -> dict:
    """
    Rule-based fallback deal probability when AI is unavailable.
    """
    base_probability = activities.get("probability", 50)
    factors = []
    probability_adjustment = 0

    # Engagement scoring
    total_engagement = (
        activities.get("total_communications", 0) * 2
        + activities.get("total_calls", 0) * 3
        + activities.get("total_notes", 0) * 1
    )

    if total_engagement > 15:
        probability_adjustment += 10
        factors.append(
            {"action": "high_engagement", "priority": "medium", "reason": "Strong engagement improves close probability"}
        )
    elif total_engagement > 5:
        probability_adjustment += 5
    elif total_engagement == 0:
        probability_adjustment -= 10
        factors.append(
            {"action": "no_engagement", "priority": "high", "reason": "No engagement - needs attention"}
        )

    # Recency scoring
    days_inactive = activities.get("days_since_last_activity", 0)
    if days_inactive > 21:
        probability_adjustment -= 15
        factors.append(
            {"action": "re-engage_customer", "priority": "high", "reason": "Deal is stale - re-engagement needed"}
        )
    elif days_inactive > 14:
        probability_adjustment -= 8
        factors.append(
            {"action": "follow_up", "priority": "medium", "reason": "No recent contact - schedule follow-up"}
        )
    elif days_inactive <= 2:
        probability_adjustment += 5
        factors.append(
            {"action": "momentum", "priority": "low", "reason": "Recent activity suggests momentum"}
        )

    # Status-based adjustment
    status_type = activities.get("status_type", "Open")
    if status_type == "Won":
        probability_adjustment = 100 - base_probability
    elif status_type == "Lost":
        probability_adjustment = -base_probability
    elif status_type == "On Hold":
        probability_adjustment -= 10

    # Calculate next action
    if days_inactive > 7:
        next_action = "Schedule a follow-up call"
    elif activities.get("total_calls", 0) == 0:
        next_action = "Make initial discovery call"
    elif activities.get("total_communications", 0) < 3:
        next_action = "Send introductory email"
    else:
        next_action = "Continue nurturing"

    final_probability = max(0, min(100, base_probability + probability_adjustment))

    return {
        "probability": final_probability,
        "confidence": 0.5,  # Lower confidence for rule-based
        "next_action": next_action,
        "recommendations": factors,
        "summary": "Rule-based probability (AI unavailable)",
    }

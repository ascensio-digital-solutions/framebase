# Framebase 2.0 — Knowledge & Repo Scout Digest (Pass 2A)

- **Generated At**: `2026-11-04T15:10:02.413338+00:00`
- **Vertex AI Project**: `ascensio-media-os` (`global`, `gemini-3.8-flash`)
- **Source Folder**: `/Users/vincent/Downloads/Google Drive Images Export/isolated_reference_screenshots`
- **Total Evaluated**: `5` (`5` actionable tools/workflows)

## Discovered Tools, Workflows & Repositories

| # | Screenshot | Tool / Repo | Category Subfolder | License | Actionable | Why Relevant to Vincent |
|---|------------|-------------|--------------------|---------|------------|-------------------------|
| 1 | `(OB Pipeline) If Deal Stage is Invoiced_Payment + Quote is Paid = Move Deal Stage To Create Order.png` | **HubSpot Workflows** | `ai_and_automation/crm-and-sales` | `paid` | `Yes` | Automated CRM pipeline logic for Hair Solutions Co. onboarding flow moving deals to Create Order stage upon paid quote. |
| 2 | `(Single Order Pipeline) - DP_Quote Paid - Move Deal Stage + Create order.png` | **HubSpot Workflows** | `ai_and_automation/crm-and-sales` | `paid` | `Yes` | Automates deal property updates and order task assignments upon quote payment in CRM pipeline. |
| 3 | `(Single Unit Pipeline)  If deal stage is _Order Shipped_ = Change Properties + Create Follow-up Tasks.png` | **HubSpot Workflows** | `ai_and_automation/crm-and-sales` | `paid` | `Yes` | Automates order status updates and follow-up task creation when hair system deals reach Order Shipped stage. |
| 4 | `(Single Unit Pipeline) Deal stage is _Order Ready to Ship_ = Create Task Send Shipping Confirmation Email.png` | **HubSpot Workflows** | `ai_and_automation/crm-and-sales` | `paid` | `Yes` | Automated deal workflow in HubSpot to trigger task creation and shipping confirmation emails when an order stage updates. |
| 5 | `(Single Unit Pipeline) When deal stage is _Order Completed_ = Change Deal Stage + Tasks.png` | **HubSpot Workflows** | `ai_and_automation/crm-and-sales` | `paid` | `Yes` | Automated CRM deal pipeline workflow for handling hair system order fulfillment, invoice generation, and shipping status updates. |

## Full Structured Classifications (JSON)

### 1. `(OB Pipeline) If Deal Stage is Invoiced_Payment + Quote is Paid = Move Deal Stage To Create Order.png`
```json
{
  "capture_type": "screenshot",
  "domain": "knowledge_and_tools",
  "category": "knowledge/ai_and_automation",
  "privacy_flag": "safe",
  "subject_count": "none",
  "model_shot_type": "not_model",
  "hair_color_family": "not_applicable",
  "hair_color_code": null,
  "swatch_sub_type": "none",
  "knowledge_opportunity": {
    "is_actionable_repo_or_tool": true,
    "tool_or_repo_name": "HubSpot Workflows",
    "github_or_url": "https://www.hubspot.com",
    "license_type": "paid",
    "category_subfolder": "crm-and-sales",
    "why_relevant_to_vincent": "Automated CRM pipeline logic for Hair Solutions Co. onboarding flow moving deals to Create Order stage upon paid quote."
  },
  "app_name": "HubSpot",
  "creator_handle": null,
  "subject_or_tool_discussed": "HubSpot Workflows",
  "is_shopping": false,
  "business_evidence": null,
  "hairline_presentation": null,
  "business_quality": null,
  "photo_role": null,
  "sensitivity": "none",
  "quality": "keeper",
  "quality_issues": [],
  "tags": [
    "app:hubspot",
    "tool:hubspot-workflows",
    "workflow:automation",
    "pipeline:onboarding",
    "crm:sales-pipeline",
    "topic:quote-to-order"
  ],
  "has_vincent": false,
  "confidence": 0.98,
  "rationale": "HubSpot CRM workflow diagram detailing automation branches and deal stage updates upon quote payment for onboarding orders."
}
```

### 2. `(Single Order Pipeline) - DP_Quote Paid - Move Deal Stage + Create order.png`
```json
{
  "capture_type": "screenshot",
  "domain": "knowledge_and_tools",
  "category": "knowledge/ai_and_automation",
  "privacy_flag": "safe",
  "subject_count": "none",
  "model_shot_type": "not_model",
  "hair_color_family": "not_applicable",
  "hair_color_code": null,
  "swatch_sub_type": "none",
  "knowledge_opportunity": {
    "is_actionable_repo_or_tool": true,
    "tool_or_repo_name": "HubSpot Workflows",
    "github_or_url": "https://hubspot.com",
    "license_type": "paid",
    "category_subfolder": "crm-and-sales",
    "why_relevant_to_vincent": "Automates deal property updates and order task assignments upon quote payment in CRM pipeline."
  },
  "app_name": "HubSpot",
  "creator_handle": null,
  "subject_or_tool_discussed": "HubSpot Deal & Quote Automation Workflow",
  "is_shopping": false,
  "business_evidence": null,
  "hairline_presentation": null,
  "business_quality": null,
  "photo_role": null,
  "sensitivity": "none",
  "quality": "keeper",
  "quality_issues": null,
  "tags": [
    "tool:hubspot",
    "category:crm",
    "workflow:automation",
    "sales:quote",
    "pipeline:deals"
  ],
  "has_vincent": false,
  "confidence": 0.95,
  "rationale": "HubSpot CRM workflow diagram automating deal stage updates and unit ordering tasks when quote payment is completed."
}
```

### 3. `(Single Unit Pipeline)  If deal stage is _Order Shipped_ = Change Properties + Create Follow-up Tasks.png`
```json
{
  "capture_type": "screenshot",
  "domain": "knowledge_and_tools",
  "category": "knowledge/ai_and_automation",
  "privacy_flag": "safe",
  "subject_count": "none",
  "model_shot_type": "not_model",
  "hair_color_family": "not_applicable",
  "hair_color_code": null,
  "swatch_sub_type": "none",
  "knowledge_opportunity": {
    "is_actionable_repo_or_tool": true,
    "tool_or_repo_name": "HubSpot Workflows",
    "github_or_url": "https://hubspot.com",
    "license_type": "paid",
    "category_subfolder": "crm-and-sales",
    "why_relevant_to_vincent": "Automates order status updates and follow-up task creation when hair system deals reach Order Shipped stage."
  },
  "app_name": "HubSpot",
  "creator_handle": null,
  "subject_or_tool_discussed": "HubSpot Deal Workflow Automation",
  "is_shopping": false,
  "business_evidence": null,
  "hairline_presentation": null,
  "business_quality": null,
  "photo_role": null,
  "sensitivity": "none",
  "quality": "keeper",
  "quality_issues": [],
  "tags": [
    "tool:hubspot",
    "topic:crm-automation",
    "topic:deal-pipeline",
    "workflow:order-shipped",
    "type:screenshot"
  ],
  "has_vincent": false,
  "confidence": 0.98,
  "rationale": "HubSpot Deal enrollment workflow configuring properties and follow-up tasks when a deal reaches Order Shipped in the Single Unit pipeline."
}
```

### 4. `(Single Unit Pipeline) Deal stage is _Order Ready to Ship_ = Create Task Send Shipping Confirmation Email.png`
```json
{
  "capture_type": "screenshot",
  "domain": "knowledge_and_tools",
  "category": "knowledge/ai_and_automation",
  "privacy_flag": "safe",
  "subject_count": "none",
  "model_shot_type": "not_model",
  "hair_color_family": "not_applicable",
  "hair_color_code": null,
  "swatch_sub_type": "none",
  "knowledge_opportunity": {
    "is_actionable_repo_or_tool": true,
    "tool_or_repo_name": "HubSpot Workflows",
    "github_or_url": "https://www.hubspot.com",
    "license_type": "paid",
    "category_subfolder": "crm-and-sales",
    "why_relevant_to_vincent": "Automated deal workflow in HubSpot to trigger task creation and shipping confirmation emails when an order stage updates."
  },
  "app_name": "HubSpot",
  "creator_handle": null,
  "subject_or_tool_discussed": "HubSpot Workflows",
  "is_shopping": false,
  "business_evidence": null,
  "hairline_presentation": null,
  "business_quality": null,
  "photo_role": null,
  "sensitivity": "none",
  "quality": "keeper",
  "quality_issues": null,
  "tags": [
    "app:hubspot",
    "tool:crm",
    "workflow:automation",
    "pipeline:deals",
    "crm:sales"
  ],
  "has_vincent": false,
  "confidence": 0.98,
  "rationale": "Screenshot of a HubSpot automated deal workflow triggering an order shipped task for Single Unit pipeline deals."
}
```

### 5. `(Single Unit Pipeline) When deal stage is _Order Completed_ = Change Deal Stage + Tasks.png`
```json
{
  "capture_type": "screenshot",
  "domain": "knowledge_and_tools",
  "category": "knowledge/ai_and_automation",
  "privacy_flag": "safe",
  "subject_count": "none",
  "model_shot_type": "not_model",
  "hair_color_family": "not_applicable",
  "hair_color_code": null,
  "swatch_sub_type": "none",
  "knowledge_opportunity": {
    "is_actionable_repo_or_tool": true,
    "tool_or_repo_name": "HubSpot Workflows",
    "github_or_url": "https://hubspot.com",
    "license_type": "paid",
    "category_subfolder": "crm-and-sales",
    "why_relevant_to_vincent": "Automated CRM deal pipeline workflow for handling hair system order fulfillment, invoice generation, and shipping status updates."
  },
  "app_name": "HubSpot",
  "creator_handle": null,
  "subject_or_tool_discussed": "HubSpot Deal Automation Workflow",
  "is_shopping": false,
  "business_evidence": null,
  "hairline_presentation": null,
  "business_quality": null,
  "photo_role": null,
  "sensitivity": "none",
  "quality": "keeper",
  "quality_issues": [],
  "tags": [
    "app:hubspot",
    "tool:hubspot-workflows",
    "crm:pipeline",
    "automation:deal-flow",
    "workflow:order-completed"
  ],
  "has_vincent": false,
  "confidence": 0.98,
  "rationale": "HubSpot CRM deal enrollment workflow diagram routing single-unit orders by payment status to automate tasks and stage changes."
}
```

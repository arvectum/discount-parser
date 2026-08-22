from __future__ import annotations

from fastapi import APIRouter

from src.web.customer_feedback_13 import (
    customer_confirm_assisted_source,
    customer_confirm_existing_source,
    customer_existing_source_analysis,
    customer_mapping_redirect,
    customer_source_analysis_page,
    customer_source_settings_page,
    customer_source_settings_save,
    customer_source_test,
)

router = APIRouter()

# These exact customer routes are intentionally registered before the older
# broad /sources-registry/{source_id}/{action} route. That keeps a normal
# customer click out of the legacy manual-selector UI while preserving the old
# implementation as a developer-only fallback.
router.add_api_route('/sources-registry/analyze', customer_source_analysis_page, methods=['POST'])
router.add_api_route('/sources-registry/confirm-auto', customer_confirm_assisted_source, methods=['POST'])
router.add_api_route('/sources-registry/{source_id}/settings', customer_source_settings_page, methods=['GET'])
router.add_api_route('/sources-registry/{source_id}/settings', customer_source_settings_save, methods=['POST'])
router.add_api_route('/sources-registry/{source_id}/analyze-auto', customer_existing_source_analysis, methods=['POST'])
router.add_api_route('/sources-registry/{source_id}/confirm-auto', customer_confirm_existing_source, methods=['POST'])
router.add_api_route('/sources-registry/{source_id}/mapping', customer_mapping_redirect, methods=['GET'])
router.add_api_route('/sources-registry/{source_id}/test', customer_source_test, methods=['POST'])

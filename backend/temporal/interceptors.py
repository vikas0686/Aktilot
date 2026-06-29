"""
Temporal worker interceptor that emits custom OTel metrics for every activity.

Tracks:
  - Activity execution duration (rag_workflow_activity_duration_ms)
  - Activity retry attempts (rag_workflow_retries_total)
  - Activity terminal failures (rag_workflow_activity_failures_total)

Complements the Temporal SDK built-in metrics (temporal_activity_*) which
track scheduling latency and aggregate success/failure counts.
"""

import time
from typing import Any, Optional, Type

import temporalio.activity as _activity
from temporalio.worker import (
    ActivityInboundInterceptor,
    ExecuteActivityInput,
    Interceptor,
    WorkflowInboundInterceptor,
    WorkflowInterceptorClassInput,
)

import observability.metrics as m


class _ActivityMetricsInterceptor(ActivityInboundInterceptor):
    async def execute_activity(self, input: ExecuteActivityInput) -> Any:
        info = _activity.info()
        attrs = {
            "rag_activity_name": info.activity_type,
            "rag_workflow_type": info.workflow_type,
        }

        if info.attempt > 1:
            m.workflow_retries_total.add(1, attrs)

        t = time.monotonic()
        try:
            result = await super().execute_activity(input)
            m.workflow_activity_duration.record((time.monotonic() - t) * 1000, attrs)
            return result
        except Exception:
            m.workflow_activity_failures_total.add(1, attrs)
            raise


class MetricsInterceptor(Interceptor):
    """Register with Worker(interceptors=[MetricsInterceptor()]) alongside TracingInterceptor."""

    def intercept_activity(
        self, next: ActivityInboundInterceptor
    ) -> ActivityInboundInterceptor:
        return _ActivityMetricsInterceptor(next)

    def workflow_interceptor_class(
        self, input: WorkflowInterceptorClassInput
    ) -> Optional[Type[WorkflowInboundInterceptor]]:
        return None

"""Runtime event-loop lifecycle helpers."""
from __future__ import annotations

from core.runtime.app_runtime import clear_app_runtime


def run_runtime_event_loop(handles) -> int:
    """Run the built chat app event loop and always clean up runtime resources."""
    try:
        handles.workers.start_all()
        handles.window.show()
        from core.runtime.update_lifecycle import schedule_update_healthcheck
        schedule_update_healthcheck()
        return handles.app.exec()
    finally:
        try:
            try:
                wiring = getattr(handles, "signal_wiring_handles", None)
                controller = getattr(wiring, "turn_controller", None)
                if controller is not None:
                    controller.shutdown()
                handles.workers.stop_all()
            finally:
                try:
                    handles.chat_history.save()
                finally:
                    mcp_controller = getattr(handles, "mcp_controller", None)
                    if mcp_controller is not None:
                        mcp_controller.close_all()
        finally:
            clear_app_runtime()

from core.runtime.tool_loop import run_serial_tool_loop
from core.runtime.cancellation import check_cancelled


def run_user_turn(
    llm_manager, tool_manager, user_text, max_loops=6, loop_runner=run_serial_tool_loop, progress_callback=None,
    text_callback=None,
):
    working_messages = llm_manager.get_messages()
    working_messages.append(llm_manager.build_user_message(user_text))

    loop_kwargs = {
        "messages": working_messages,
        "adapter": llm_manager.adapter,
        "tool_manager": tool_manager,
        "generation_config": llm_manager.get_generation_config(),
        "max_loops": max_loops,
    }
    if loop_runner is run_serial_tool_loop:
        loop_kwargs["context_limit"] = getattr(llm_manager, "max_tokens", 128000)
    if progress_callback is not None:
        loop_kwargs["progress_callback"] = progress_callback
    if text_callback is not None:
        loop_kwargs["text_callback"] = text_callback
    result = loop_runner(**loop_kwargs)

    check_cancelled()
    llm_manager.set_messages(result.updated_messages)
    return result

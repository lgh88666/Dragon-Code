"""所有本地工具共用的接口和执行保护。"""

import asyncio

from pydantic import BaseModel, ValidationError

from dragon_code.models import ToolCall, ToolDefinition, ToolResult


class ToolExecutionError(Exception):
    """工具主动报告的可预期错误。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class Tool:
    """六个具体工具共用的简单基类。"""

    name = ""
    description = ""
    category = ""
    read_only = True
    destructive = False
    is_concurrency_safe = True
    arguments_model: type[BaseModel]
    timeout_seconds = 30.0

    def definition(self) -> ToolDefinition:
        """生成给模型看的工具定义。"""

        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.arguments_model.model_json_schema(),
            category=self.category,
            read_only=self.read_only,
            destructive=self.destructive,
            is_concurrency_safe=self.is_concurrency_safe,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """统一校验参数、限制超时并包装错误。"""

        if call.arguments is None:
            return self._failure(call, "invalid_json", call.parse_error or "工具参数不是有效 JSON。")

        try:
            arguments = self.arguments_model.model_validate(call.arguments)
            return await asyncio.wait_for(
                self.run(call, arguments),
                timeout=self.timeout_seconds,
            )
        except asyncio.CancelledError:
            raise
        except ValidationError as error:
            return self._failure(call, "invalid_arguments", str(error))
        except TimeoutError:
            return self._failure(call, "timeout", f"工具执行超过 {self.timeout_seconds:g} 秒。")
        except ToolExecutionError as error:
            return self._failure(call, error.code, error.message)
        except Exception:
            # 不把本机路径、命令环境或堆栈细节回灌给模型。
            return self._failure(call, "tool_error", "工具执行失败，请检查参数后重试。")

    async def run(self, call: ToolCall, arguments: BaseModel) -> ToolResult:
        """由具体工具实现真正的操作。"""

        raise NotImplementedError

    def _success(
        self,
        call: ToolCall,
        content: str,
        *,
        metadata: dict | None = None,
        truncated: bool = False,
    ) -> ToolResult:
        return ToolResult(
            call_id=call.id,
            tool_name=self.name,
            success=True,
            content=content,
            metadata=metadata or {},
            truncated=truncated,
        )

    def _failure(self, call: ToolCall, code: str, message: str) -> ToolResult:
        return ToolResult(
            call_id=call.id,
            tool_name=call.name or self.name,
            success=False,
            error_code=code,
            error_message=message,
        )

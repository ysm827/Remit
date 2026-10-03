"""按配置装配各角色 LLM 实例的工厂。"""

from app.config.setting import Settings, settings
from app.core.llm.llm import LLM


def _agent_llm(cfg: Settings, role: str, task_id: str) -> LLM:
    """按角色前缀（COORDINATOR 等）读取一组配置并实例化。"""
    model = LLM(
        api_type=getattr(cfg, f"{role}_API_TYPE"),
        api_key=getattr(cfg, f"{role}_API_KEY"),
        model=getattr(cfg, f"{role}_MODEL"),
        base_url=getattr(cfg, f"{role}_BASE_URL"),
        task_id=task_id,
        max_tokens=getattr(cfg, f"{role}_MAX_TOKENS"),
        reasoning_effort=getattr(cfg, f"{role}_REASONING_EFFORT", None),
        context_window=getattr(cfg, f"{role}_CONTEXT_WINDOW", 128000),
    )
    model.capability_role = role.lower()
    if role in {
        "COORDINATOR",
        "MODELER",
        "CODER",
        "WRITER",
        "MODEL_SCOUT",
        "MODEL_CRITIC",
    }:
        from app.services.model_capabilities import load_profile

        model.capabilities = load_profile(role.lower(), cfg)
    return model


class LLMFactory:
    """为一个任务创建全部角色共享 task_id 的 LLM 集合。"""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id

    def get_all_llms(self) -> tuple[LLM, LLM, LLM, LLM]:
        """返回 ``(协调, 建模, 编码, 写作)`` 四个角色的 LLM。"""
        return (
            _agent_llm(settings, "COORDINATOR", self.task_id),
            _agent_llm(settings, "MODELER", self.task_id),
            _agent_llm(settings, "CODER", self.task_id),
            _agent_llm(settings, "WRITER", self.task_id),
        )

    def get_modeling_llms(self) -> tuple[LLM, LLM, LLM]:
        """建模流程只初始化协调、建模与编码角色。"""
        return tuple(
            _agent_llm(settings, role, self.task_id)
            for role in ("COORDINATOR", "MODELER", "CODER")
        )

    def get_writer_llm(self) -> LLM:
        """论文工作区按需初始化独立写作角色。"""
        return _agent_llm(settings, "WRITER", self.task_id)

    def get_vision_llm(self) -> LLM:
        """识图模型；VISION_* 未配置时复用协调者接入。

        Raises:
            ValueError: 协调者与 VISION_* 都没有可用配置。
        """
        from app.services.model_capabilities import role_config, load_profile

        config = role_config("vision", settings)
        if not config["api_key"] or not config["model_id"]:
            raise ValueError("识图未配置模型：请填写 VISION_* 或 COORDINATOR_* 配置")
        model = LLM(
            api_type=config["api_type"],
            api_key=config["api_key"],
            model=config["model_id"],
            base_url=config["base_url"],
            task_id=self.task_id,
            max_tokens=config["max_tokens"],
            context_window=config["context_window"],
        )
        model.capability_role = "vision"
        model.capabilities = load_profile("vision", settings)
        return model

    def get_model_council_llms(self) -> tuple[LLM, LLM]:
        """返回评审组使用的 ``(探索者, 盲审者)`` LLM。

        Raises:
            ValueError: 已启用评审组但配置不完整。
        """
        missing = [
            f"{role}_{field}"
            for role in ("MODEL_SCOUT", "MODEL_CRITIC")
            for field in ("API_TYPE", "API_KEY", "MODEL")
            if not getattr(settings, f"{role}_{field}")
        ]
        if missing:
            raise ValueError("已启用模型评审组，但配置不完整：" + "、".join(missing))
        return (
            _agent_llm(settings, "MODEL_SCOUT", self.task_id),
            _agent_llm(settings, "MODEL_CRITIC", self.task_id),
        )

import { resultOverview } from "@/pages/team/resultOverview";
import { expect, it } from "vitest";

it("不把自检通过或文件存在当作复核通过", () => {
 expect(resultOverview("ques1", {quality_report:{status:"pass"},artifacts:["a.csv"]}).tone).toBe("pending");
 expect(resultOverview("ques1", {quality_report:{status:"pass"},modeler_review:{verdict:"manual_review"}}).tone).toBe("attention");
 expect(resultOverview("ques1", {quality_report:{status:"pass",robustness_checks:[{passed:false}]},modeler_review:{verdict:"accept"}}).tone).toBe("attention");
});

it("准确保留零值和基准，不把敏感性场景当主结果", () => {
 const result=resultOverview("ques2",{quality_report:{type_specific:{objective:{model_value:0,baseline_value:1},sensitivity_scenarios:[{obj:999}]}},modeler_review:{verdict:"accept"}});
 expect(result.metrics).toEqual([{name:"目标函数值",value:"0",baseline:"1"}]);
 expect(result.status).toBe("复核通过");
});

it("优先展示已有核心结果，保留完整原文供追溯", () => {
 const text="失败原因：旧脚本错误\n\n## 二、核心结果\n能耗 59.6276 kWh。\n\n## 三、文件\na.csv";
 const result=resultOverview("ques1",{coder_response:{code_response:text}});
 expect(result.excerpt).toBe("能耗 59.6276 kWh。");
 expect(result.narrative).toBe(text);
});

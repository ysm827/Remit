export const roleLabels: Record<string, string> = {
	coordinator: "Remit",
	modeler: "建模",
	coder: "计算",
	writer: "论文",
	all: "全体角色",
	user: "你",
};

export const teamMembers = [
 { role: "coordinator", name: "团团", job: "协调手", description: "拆题带路，帮你抓住重点", prompt: "团团，我第一次参加数模比赛，可以陪我梳理一下从读题到交付的步骤吗？" },
 { role: "modeler", name: "灵灵", job: "建模手", description: "选模型，也讲清为什么", prompt: "灵灵，拿到赛题后，该怎样判断适合用什么模型？请用一个小例子解释。" },
 { role: "coder", name: "点点", job: "代码手", description: "读数据，动手算，认真验", prompt: "点点，开始计算前，数据一般需要检查哪些问题？" },
 { role: "writer", name: "墨墨", job: "论文手", description: "让每个结论都有据可讲", prompt: "墨墨，一篇清楚的数模论文应该怎样组织？哪些计算证据需要提前留好？" },
];

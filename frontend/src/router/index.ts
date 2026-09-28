import {
	type RouteRecordRaw,
	createRouter,
	createWebHistory,
} from "vue-router";

const TeamChat = () => import("@/pages/team/TeamChat.vue");

/** 路由表：历史入口统一收敛到 /home，任务页同时兼容新旧两种路径。 */
const routes: RouteRecordRaw[] = [
	{ path: "/", redirect: "/home" },
	{ path: "/home", component: TeamChat },
	{ path: "/projects", redirect: "/home" },
	{
		path: "/writing",
		redirect: "/home",
	},
	{
		path: "/writing/:task_id",
		redirect: (route) => ({
			path: `/project/${route.params.task_id}`,
			query: { view: "paper" },
		}),
	},
	{
		path: "/project/:projectId/paper",
		redirect: (route) => `/writing/${route.params.projectId}`,
	},
	// 旧版入口保留为重定向，避免外链失效
	{ path: "/landing", redirect: "/home" },
	{ path: "/login", redirect: "/home" },
	{ path: "/chat", redirect: "/home?new=1" },
	{
		path: "/task/:task_id",
		component: TeamChat,
		props: true,
	},
	{
		path: "/project/:projectId",
		component: TeamChat,
		props: (route) => ({ task_id: route.params.projectId }),
	},
	{
		path: "/project/:projectId/:stage",
		redirect: (route) => ({
			path: `/project/${route.params.projectId}`,
			query: { view: "files" },
		}),
	},
];

export default createRouter({
	history: createWebHistory(),
	routes,
});

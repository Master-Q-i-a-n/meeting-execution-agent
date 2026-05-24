import { createRouter, createWebHashHistory } from "vue-router";

import AskView from "@/views/AskView.vue";
import DraftReviewView from "@/views/DraftReviewView.vue";
import ExecutionBoardView from "@/views/ExecutionBoardView.vue";
import IntegrationsView from "@/views/IntegrationsView.vue";
import MeetingsView from "@/views/MeetingsView.vue";
import TraceView from "@/views/TraceView.vue";
import UploadView from "@/views/UploadView.vue";

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", redirect: "/meetings" },
    { path: "/meetings", component: MeetingsView },
    { path: "/upload", component: UploadView },
    { path: "/draft-review", component: DraftReviewView },
    { path: "/board", component: ExecutionBoardView },
    { path: "/ask", component: AskView },
    { path: "/integrations", component: IntegrationsView },
    { path: "/trace", component: TraceView },
  ],
});

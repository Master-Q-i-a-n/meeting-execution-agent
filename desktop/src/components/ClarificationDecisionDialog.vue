<script setup lang="ts">
import type { UnconfirmedItemDraft } from "@/api/types";

defineProps<{
  open: boolean;
  loading?: boolean;
  unconfirmedItems: UnconfirmedItemDraft[];
}>();

defineEmits<{
  close: [];
  addInfo: [];
  directDispatch: [];
}>();
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" role="presentation">
      <section class="decision-dialog" role="dialog" aria-modal="true" aria-labelledby="clarification-dialog-title">
        <div class="dialog-heading">
          <p class="dialog-kicker">Needs clarification</p>
          <h2 id="clarification-dialog-title">草稿还有待澄清信息</h2>
        </div>

        <p class="dialog-copy">
          当前工作流停在待澄清节点，还有 {{ unconfirmedItems.length }} 个问题没有确认。
          你可以先补充负责人、截止时间等信息后重新抽取；如果你确认当前草稿已经可以执行，也可以跳过澄清并直接派送到 Linear。
        </p>

        <ul v-if="unconfirmedItems.length" class="dialog-question-list">
          <li v-for="item in unconfirmedItems.slice(0, 4)" :key="item.id">
            {{ item.question }}
          </li>
        </ul>

        <div class="dialog-actions">
          <button class="outline-button" :disabled="loading" @click="$emit('addInfo')">
            先补充信息
          </button>
          <button class="primary-button" :disabled="loading" @click="$emit('directDispatch')">
            {{ loading ? "正在继续..." : "直接派送" }}
          </button>
          <button class="text-button" :disabled="loading" @click="$emit('close')">
            取消
          </button>
        </div>
      </section>
    </div>
  </Teleport>
</template>

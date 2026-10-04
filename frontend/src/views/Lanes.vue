<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const refill = ref<any>(null)
const packInputs = ref<Record<number, string>>({})
const saving = ref<number | null>(null)
const error = ref('')

async function reload() {
  rows.value = await api('/lanes')
  for (const r of rows.value) packInputs.value[r.id] = r.case_pack == null ? '' : String(r.case_pack)
}
onMounted(async () => {
  await reload()
  try { refill.value = await api('/refills/run?location_id=1', { method: 'POST' }) } catch { /* */ }
})

async function savePack(r: any) {
  error.value = ''
  const raw = (packInputs.value[r.id] ?? '').trim()
  const pack = raw === '' ? null : Number(raw)
  if (pack !== null && (!Number.isInteger(pack) || pack <= 0)) {
    error.value = `${r.slot_no} 箱规必须为正整数（留空表示按件补）`
    // illegal pack is never accepted by the card: snap input back to the saved value
    packInputs.value[r.id] = r.case_pack == null ? '' : String(r.case_pack)
    return
  }
  saving.value = r.id
  try {
    // 同一次提交：货道箱规 + 该点位最新补货单一起改；失败则一起回滚
    await api(`/lanes/${r.id}`, { method: 'PUT', body: JSON.stringify({ case_pack: pack }) })
    await reload()
    refill.value = await api('/refills/latest?location_id=1')
  } catch (e: any) {
    error.value = `${r.slot_no} 保存失败：箱规与补货单均未改动（${e?.message ?? e}）`
    // server rolled everything back; card input must show the saved pack too
    packInputs.value[r.id] = r.case_pack == null ? '' : String(r.case_pack)
  } finally {
    saving.value = null
  }
}
</script>
<template>
  <h1>货道格子</h1>
  <p class="sub">机面货道网格 · 格内库存条 · 箱规保存即重写最新补货单</p>
  <p v-if="error" class="vf-error">{{ error }}</p>
  <div class="vf-machine-layout">
    <div class="vf-slot-grid">
      <div v-for="r in rows" :key="r.id" class="vf-slot">
        <div class="vf-slot-no">{{ r.slot_no }}</div>
        <div class="vf-slot-sku">{{ r.sku_name }}</div>
        <div class="vf-slot-bar">
          <div
            class="vf-slot-fill"
            :class="{ 'vf-need': r.gap > 0 }"
            :style="{ width: Math.min(r.fill_pct, 100) + '%' }"
          />
        </div>
        <div class="vf-slot-meta">{{ r.stock }}/{{ r.capacity }} · 缺 {{ r.gap }}</div>
        <div class="vf-slot-meta">箱规 {{ r.case_pack ?? '按件' }}</div>
        <div class="vf-pack-edit">
          <input
            v-model="packInputs[r.id]"
            type="number"
            min="1"
            step="1"
            placeholder="按件"
            title="箱规（件/箱），留空按件补"
            @keyup.enter="savePack(r)"
          />
          <button class="vf-pack-btn" :disabled="saving === r.id" @click="savePack(r)">存</button>
        </div>
      </div>
    </div>
    <aside class="vf-receipt" v-if="refill">
      <h2>*** 补货建议单 ***</h2>
      <div class="vf-receipt-line" v-for="l in refill.lines" :key="l.lane_id">
        <span>{{ l.slot_no }} {{ l.sku_name }}</span>
        <span v-if="l.status === 'need_fill' && l.fill_qty === 0">不足整箱<small v-if="l.case_pack > 1"> · 箱{{ l.case_pack }}</small></span>
        <span v-else>x{{ l.fill_qty }}<small v-if="l.case_pack > 1"> 箱{{ l.case_pack }}</small></span>
      </div>
      <p class="muted" style="margin:0.75rem 0 0;font-size:0.72rem;color:#6a5e48;text-align:center">
        — 机面打印预览 —
      </p>
    </aside>
  </div>
</template>

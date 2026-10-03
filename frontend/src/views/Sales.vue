<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
onMounted(async () => { rows.value = await api('/sales') })
</script>
<template>
  <h1>销量</h1>
  <p class="sub">近期出货记录</p>
  <div class="card">
    <table>
      <thead><tr><th>货道</th><th>商品</th><th>数量</th><th>时间</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)"><td>{{ r.slot_no }}</td><td>{{ r.sku_name }}</td><td>{{ r.qty }}</td><td>{{ r.sold_at }}</td></tr>
      </tbody>
    </table>
  </div>
</template>

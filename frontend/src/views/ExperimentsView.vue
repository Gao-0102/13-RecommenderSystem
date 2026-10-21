<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'
import http from '../api'
import { useRemote } from '../composables/useRemote'
import type { Algorithm, HistoryUser, Movie, Page } from '../types'
import StatePanel from '../components/StatePanel.vue'
import PageNav from '../components/PageNav.vue'
import AlgorithmPanel from '../components/AlgorithmPanel.vue'
const route = useRoute(), router = useRouter(), auth = useAuth()
const source = ref('ml'), algorithm = ref('content'), selected = ref('')
const userPage = ref(1), users = useRemote<Page<HistoryUser>>(), ratings = useRemote<Page<Movie>>()
const ratingPage = ref(1), available = ref<Algorithm[]>([]), registryError = ref<unknown>(null)
const algorithmGroups = computed(() => [
  { label: '个性化推荐', items: available.value.filter(a => ['content', 'itemcf', 'als'].includes(a.algorithm)) },
  { label: '热门与新用户', items: available.value.filter(a => ['popular', 'cold_start'].includes(a.algorithm)) },
])
const algorithmNames: Record<string, string> = { content: '内容推荐', itemcf: 'ItemCF', als: 'Spark ALS', popular: '热门榜单', cold_start: '新用户冷启动' }
const algorithmLabel = computed(() => algorithmNames[algorithm.value] || algorithm.value)
const subject = computed(() => source.value === 'ml' ? (selected.value ? `ml:${selected.value}` : '') : auth.account?.subject_key || '')
const endpoint = computed(() => !subject.value ? null : source.value === 'ml' ? `/demo/history-users/${selected.value}/recommendations/${algorithm.value}` : `/me/recommendations/${algorithm.value}`)
function updateUrl() { void router.replace({ path:'/experiments', query:{ source:source.value, algorithm:algorithm.value, ...(selected.value ? {user:selected.value} : {}) } }) }
async function fetchUsers(page = userPage.value) { userPage.value = page; await users.load(async () => (await http.get<Page<HistoryUser>>('/demo/history-users',{params:{page,per_page:20}})).data) }
function fetchRatings() { if (source.value !== 'ml' || !selected.value) return; return ratings.load(async () => (await http.get<Page<Movie>>(`/demo/history-users/${encodeURIComponent(selected.value)}/ratings`,{params:{page:ratingPage.value,per_page:10}})).data) }
async function fetchRegistry() { try { available.value=(await http.get<{items:Algorithm[]}>('/experiments/algorithms')).data.items; registryError.value=null } catch(e) { registryError.value=e } }
watch(() => route.query, () => { source.value=route.query.source==='app'?'app':'ml'; algorithm.value=typeof route.query.algorithm==='string' && /^[a-z_]+$/.test(route.query.algorithm) ? route.query.algorithm:'content'; selected.value=typeof route.query.user==='string' && /^[1-9][0-9]*$/.test(route.query.user)?route.query.user:'' }, {immediate:true})
watch(() => [selected.value,source.value], () => {ratingPage.value=1; void fetchRatings()})
void fetchUsers(); void fetchRegistry(); void fetchRatings()
</script>
<template>
  <div class="page">
    <div class="page-heading starlab-heading">
      <p class="eyebrow">✦ RECOMMENDATION LAB ✦</p>
      <h1>推荐实验室<span class="heading-dot">.</span></h1>
      <p>从一位观众的历史出发，观察算法如何把偏好转化为下一部电影。</p>
    </div>
    <div class="lab-notice"><span class="status-pill">推荐实验室</span><p>选择一位观众和推荐策略，实时查看为他生成的片单。</p></div>
    <div class="lab-layout">
      <aside class="lab-controls">
        <h2>推荐设置</h2>
        <div class="ctrl-section">
          <label for="subject-source">用户来源</label>
          <el-select id="subject-source" v-model="source" @change="updateUrl">
            <el-option label="经典历史观众（MovieLens）" value="ml" />
            <el-option label="我的账号" value="app" />
          </el-select>
        </div>
        <div class="ctrl-section">
          <template v-if="source==='ml'">
            <label for="history-user">选择历史观众</label>
            <el-select id="history-user" v-model="selected" placeholder="请选择一位历史观众" @change="updateUrl">
              <el-option v-for="u in users.data.value?.items" :key="u.ml_user_id" :label="`观众 #${u.ml_user_id}`" :value="u.ml_user_id" />
            </el-select>
            <StatePanel v-if="users.error.value" :error="users.error.value" @retry="fetchUsers()" />
            <p v-if="users.loading.value" class="muted" role="status">正在加载观众列表…</p>
            <div class="user-pager">
              <el-button :disabled="userPage===1 || users.loading.value" @click="fetchUsers(userPage-1)">上一组</el-button>
              <span>{{ userPage }} / {{ Math.ceil((users.data.value?.total || 0)/20) || 1 }}</span>
              <el-button :disabled="!users.data.value || userPage*20>=users.data.value.total || users.loading.value" @click="fetchUsers(userPage+1)">下一组</el-button>
            </div>
            <p class="form-hint">按顺序分页浏览全部历史观众。</p>
          </template>
          <div v-else class="current-subject">
            <p>{{ auth.account?.login_name || '还没有登录' }}</p>
            <span>{{ auth.account ? '已登录 · 将为你生成专属片单' : '登录后即可用你的账号体验推荐' }}</span>
            <RouterLink v-if="!auth.account" to="/login" class="text-link">前往登录 →</RouterLink>
          </div>
        </div>
        <div class="ctrl-section">
          <label for="algorithm-select">推荐策略</label>
          <el-select id="algorithm-select" v-model="algorithm" @change="updateUrl">
            <el-option-group v-for="group in algorithmGroups" :key="group.label" :label="group.label">
              <el-option v-for="a in group.items" :key="a.algorithm" :label="algorithmNames[a.algorithm] || a.algorithm" :value="a.algorithm" />
            </el-option-group>
          </el-select>
          <StatePanel v-if="registryError" :error="registryError" @retry="fetchRegistry" />
        </div>
      </aside>
    <div class="lab-results"><AlgorithmPanel :label="`${algorithmLabel} · 推荐结果`" :endpoint="endpoint" :empty-subject="source==='ml' ? '请选择历史用户' : '登录后体验'" /><section v-if="source==='ml'" class="history-panel"><div class="section-top"><h2>历史评分</h2><span class="status-pill">{{ selected ? `观众 #${selected}` : '未选择用户' }}</span></div><StatePanel :loading="ratings.loading.value" :error="ratings.error.value" :empty="!selected || !!ratings.data.value && !ratings.data.value.items.length" title="选择一位历史观众" description="选择用户后，这里会展示他的历史评分。" @retry="fetchRatings"><div class="table-scroll"><el-table :data="ratings.data.value?.items || []" aria-label="历史用户评分表"><el-table-column label="电影" min-width="200"><template #default="scope"><RouterLink :to="`/movies/${scope.row.movie_id}`" class="text-link">{{ scope.row.movielens_title }}</RouterLink></template></el-table-column><el-table-column prop="movie_id" label="电影ID" width="100" /><el-table-column prop="rating" label="历史评分" width="100" /></el-table></div><PageNav :page="ratingPage" :size="10" :total="ratings.data.value?.total || 0" @change="ratingPage=$event;fetchRatings()" /></StatePanel></section></div></div>
  </div>
</template>

<style scoped>
.starlab-heading .eyebrow { letter-spacing: .35em; }
.lab-controls { position: sticky; top: 108px; padding: 0; overflow: hidden; }
.lab-controls h2 { display: flex; align-items: center; gap: 8px; color: var(--text); font-size: 15px; margin: 0; padding: 20px 22px; border-bottom: 1px solid var(--border); background: linear-gradient(135deg, rgba(14,165,165,0.10), rgba(14,165,165,0.02)); }
.ctrl-section { padding: 18px 22px; }
.ctrl-section + .ctrl-section { border-top: 1px dashed var(--border); }
.lab-controls label { display: block; margin-bottom: 8px; font-size: 12px; color: var(--muted); letter-spacing: .04em; }
.lab-controls label::before { content: ''; display: inline-block; width: 5px; height: 5px; border-radius: 50%; background: var(--accent); margin-right: 8px; vertical-align: 2px; }
.form-hint { margin-top: 10px; }
.current-subject { padding: 14px 16px; border-radius: 8px; background: var(--accent-tint); border: 1px solid #0EA5A530; }
.current-subject p { font-size: 14px; font-weight: 600; color: var(--text); }
.current-subject > span { display: block; color: var(--accent); margin-top: 6px; font-size: 12px; }
</style>

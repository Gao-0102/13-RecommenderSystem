<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'
import http from '../api'
import { useRemote } from '../composables/useRemote'
import type { Algorithm, HistoryUser, Movie, Page } from '../types'
import StatePanel from '../components/StatePanel.vue'
import PageNav from '../components/PageNav.vue'
import AlgorithmPanel from '../components/AlgorithmPanel.vue'
import { Loading } from '@element-plus/icons-vue'
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

interface EvalAlg { algorithm: string; name: string; precision_at_10: number; recall_at_10: number; valid_users: number; description: string }
interface EvalMetrics { dataset_version: string; split_version: string; evaluation_file: string; train_file: string; user_count: number; top_k: number; algorithms: EvalAlg[] }
interface EvalResponse { status: string; metrics: EvalMetrics }
const evalData = ref<EvalResponse | null>(null)
const evalLoading = ref(false)
const evalError = ref<unknown>(null)
async function fetchEval() {
  evalLoading.value = true; evalError.value = null
  try { evalData.value = (await http.get<EvalResponse>('/experiments/evaluations')).data }
  catch (e) { evalError.value = e }
  finally { evalLoading.value = false }
}
onMounted(() => { void fetchEval() })
const sortedByP = computed(() => [...(evalData.value?.metrics.algorithms || [])].sort((a,b) => b.precision_at_10 - a.precision_at_10))
const maxP = computed(() => Math.max(...(evalData.value?.metrics.algorithms.map(a => a.precision_at_10) || [1])))
const maxR = computed(() => Math.max(...(evalData.value?.metrics.algorithms.map(a => a.recall_at_10) || [1])))
const medalFor = (idx: number) => ['🥇', '🥈', '🥉'][idx] || ''
const colorFor = (alg: string) => ({ content: '#0EA5A5', itemcf: '#F59E0B', als: '#8B5CF6', popular: '#EF4444' } as Record<string, string>)[alg] || '#666'
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

    <section class="eval-section">
      <div class="eval-heading">
        <p class="eyebrow">✦ ALGORITHM EVALUATION ✦</p>
        <h2>算法效果评价<span class="heading-dot">.</span></h2>
        <p class="eval-sub">基于课程统一验证数据集，对比三种推荐算法的 Top-{{ evalData?.metrics.top_k || 10 }} 推荐效果</p>
      </div>

      <div v-if="evalLoading" class="eval-loading"><el-icon class="is-loading"><Loading /></el-icon><span>正在加载评价数据…</span></div>
      <div v-else-if="evalError" class="eval-error">
        <el-alert type="error" :closable="false">评价数据加载失败<button class="text-link" @click="fetchEval">重新加载</button></el-alert>
      </div>
      <template v-else-if="evalData">
        <div class="eval-meta">
          <div class="meta-item"><span class="meta-label">验证用户</span><span class="meta-val">{{ evalData.metrics.user_count.toLocaleString() }}</span></div>
          <div class="meta-item"><span class="meta-label">Top-K</span><span class="meta-val">{{ evalData.metrics.top_k }}</span></div>
          <div class="meta-item"><span class="meta-label">数据集版本</span><span class="meta-val small">{{ evalData.metrics.dataset_version }}</span></div>
          <div class="meta-item"><span class="meta-label">切分版本</span><span class="meta-val small">{{ evalData.metrics.split_version }}</span></div>
        </div>

        <div class="eval-main">
          <div class="eval-table-wrap">
            <h3>对比表格</h3>
            <table class="eval-table">
              <thead><tr><th class="rank">#</th><th>算法</th><th>Precision@10</th><th>Recall@10</th><th>有效用户</th></tr></thead>
              <tbody>
                <tr v-for="(a, idx) in sortedByP" :key="a.algorithm" :style="{ borderLeftColor: colorFor(a.algorithm) }">
                  <td class="rank">{{ medalFor(idx) }}</td>
                  <td>
                    <div class="alg-name" :style="{ color: colorFor(a.algorithm) }">
                      <span class="alg-dot" :style="{ background: colorFor(a.algorithm) }"></span>{{ a.name }}
                    </div>
                    <div class="alg-desc">{{ a.description }}</div>
                  </td>
                  <td class="metric">{{ (a.precision_at_10 * 100).toFixed(2) }}%</td>
                  <td class="metric">{{ (a.recall_at_10 * 100).toFixed(2) }}%</td>
                  <td>{{ a.valid_users.toLocaleString() }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="eval-bars">
            <h3>Precision@10 对比</h3>
            <div v-for="a in sortedByP" :key="'p-'+a.algorithm" class="bar-row">
              <span class="bar-label">{{ a.name }}</span>
              <div class="bar-track"><div class="bar-fill" :style="{ width: (a.precision_at_10 / maxP * 100) + '%', background: colorFor(a.algorithm) }"></div></div>
              <span class="bar-val">{{ (a.precision_at_10 * 100).toFixed(2) }}%</span>
            </div>
            <h3 class="bar-title">Recall@10 对比</h3>
            <div v-for="a in sortedByP" :key="'r-'+a.algorithm" class="bar-row">
              <span class="bar-label">{{ a.name }}</span>
              <div class="bar-track"><div class="bar-fill" :style="{ width: (a.recall_at_10 / maxR * 100) + '%', background: colorFor(a.algorithm) }"></div></div>
              <span class="bar-val">{{ (a.recall_at_10 * 100).toFixed(2) }}%</span>
            </div>
          </div>
        </div>

        <div class="eval-insights">
          <h3>💡 分析洞察</h3>
          <div class="insight-cards">
            <div class="insight-card" v-for="a in sortedByP" :key="'ins-'+a.algorithm">
              <div class="insight-icon" :style="{ background: colorFor(a.algorithm) + '22', color: colorFor(a.algorithm) }">
                {{ medalFor(sortedByP.indexOf(a)) || '▸' }}
              </div>
              <div class="insight-body">
                <div class="insight-name" :style="{ color: colorFor(a.algorithm) }">{{ a.name }}</div>
                <div class="insight-metrics">P@10 = {{ (a.precision_at_10 * 100).toFixed(2) }}% · R@10 = {{ (a.recall_at_10 * 100).toFixed(2) }}%</div>
                <div class="insight-desc">{{ a.description }}</div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </section>
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

.eval-section { margin-top: 56px; padding: 32px 28px; background: linear-gradient(180deg, rgba(14,165,165,0.04), transparent); border-top: 1px solid var(--border); }
.eval-heading { text-align: center; margin-bottom: 28px; }
.eval-heading .eyebrow { letter-spacing: .35em; font-size: 11px; color: var(--accent); margin-bottom: 8px; }
.eval-heading h2 { font-size: 28px; margin: 0 0 8px; }
.eval-sub { color: var(--muted); margin: 0; font-size: 14px; }

.eval-meta { display: flex; gap: 16px; justify-content: center; margin-bottom: 28px; flex-wrap: wrap; }
.meta-item { background: var(--card, #fff); border: 1px solid var(--border); border-radius: 10px; padding: 12px 20px; text-align: center; min-width: 120px; }
.meta-label { display: block; font-size: 11px; color: var(--muted); letter-spacing: .05em; margin-bottom: 4px; }
.meta-val { font-size: 20px; font-weight: 700; color: var(--text); }
.meta-val.small { font-size: 13px; font-weight: 500; }

.eval-loading { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 40px; color: var(--muted); }
.eval-error { max-width: 600px; margin: 0 auto; }

.eval-main { display: grid; grid-template-columns: 1.2fr 1fr; gap: 24px; margin-bottom: 28px; }
.eval-main h3 { font-size: 15px; margin: 0 0 14px; color: var(--text); display: flex; align-items: center; gap: 6px; }
.eval-main h3::before { content: ''; width: 3px; height: 16px; background: var(--accent); border-radius: 2px; }

.eval-table-wrap { background: var(--card, #fff); border: 1px solid var(--border); border-radius: 12px; padding: 22px; }
.eval-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.eval-table th { text-align: left; font-weight: 600; color: var(--muted); padding: 10px 12px; font-size: 11px; letter-spacing: .05em; border-bottom: 2px solid var(--border); }
.eval-table td { padding: 14px 12px; border-bottom: 1px solid var(--border); }
.eval-table tr:last-child td { border-bottom: none; }
.eval-table tbody tr { border-left: 3px solid transparent; }
.eval-table .rank { width: 40px; font-size: 18px; text-align: center; }
.eval-table .metric { font-weight: 700; font-variant-numeric: tabular-nums; }
.alg-name { font-weight: 600; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.alg-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.alg-desc { font-size: 11px; color: var(--muted); margin-top: 3px; }

.eval-bars { background: var(--card, #fff); border: 1px solid var(--border); border-radius: 12px; padding: 22px; }
.bar-row { display: grid; grid-template-columns: 140px 1fr 70px; gap: 10px; align-items: center; margin-bottom: 10px; }
.bar-label { font-size: 12px; color: var(--muted); }
.bar-track { height: 20px; background: var(--border); border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 4px; transition: width .4s ease; min-width: 2px; }
.bar-val { font-size: 12px; font-weight: 600; text-align: right; font-variant-numeric: tabular-nums; }
.bar-title { margin-top: 22px !important; }

.eval-insights h3 { font-size: 15px; margin: 0 0 14px; color: var(--text); }
.insight-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.insight-card { display: flex; gap: 14px; background: var(--card, #fff); border: 1px solid var(--border); border-radius: 12px; padding: 18px; transition: transform .2s, box-shadow .2s; }
.insight-card:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,0.08); }
.insight-icon { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0; }
.insight-name { font-weight: 700; font-size: 14px; margin-bottom: 4px; }
.insight-metrics { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; margin-bottom: 6px; }
.insight-desc { font-size: 12px; color: var(--muted); line-height: 1.5; }

@media (max-width: 900px) {
  .eval-main { grid-template-columns: 1fr; }
  .insight-cards { grid-template-columns: 1fr; }
}
</style>

import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { fmtSeconds, fmtTime } from '../utils.js'

const fmtPct = (rate) => `${(rate * 100).toFixed(1)}%`

/**
 * 校注覆盖盲区工作台（只读，基于已保存的项目文档）。
 *
 * 按说话人统计实际发言时长、已被同名校注覆盖的时长与覆盖率，并列出未覆盖
 * 的发言区间（盲区）。点击盲区区间跳转回编辑页并按时间轴定位
 * （/projects/{id}?from=coverage&focusStart=…&focusEnd=…）。
 */
export default function CoveragePage() {
  const { id: projectId } = useParams()
  const navigate = useNavigate()
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [speakerFilter, setSpeakerFilter] = useState('') // '' = 全部说话人
  const [activeKey, setActiveKey] = useState(null)

  useEffect(() => {
    setReport(null)
    setError('')
    setSpeakerFilter('')
    setActiveKey(null)
    api.getCoverage(projectId).then(setReport).catch((e) => setError(e.message))
  }, [projectId])

  const speakers = useMemo(() => report?.speakers || [], [report])
  const shownSpeakers = useMemo(
    () => (speakerFilter
      ? speakers.filter((sp) => sp.speaker === speakerFilter)
      : speakers),
    [speakers, speakerFilter])

  const blindSpots = useMemo(() => {
    const out = []
    shownSpeakers.forEach((sp) => sp.blindSpots.forEach((b) => out.push({
      ...b, speaker: sp.speaker,
    })))
    out.sort((a, b) => a.start - b.start || a.end - b.end
      || a.speaker.localeCompare(b.speaker))
    return out
  }, [shownSpeakers])

  const totals = useMemo(() => ({
    speech: shownSpeakers.reduce((sum, sp) => sum + sp.speechSeconds, 0),
    covered: shownSpeakers.reduce((sum, sp) => sum + sp.coveredSeconds, 0),
    blind: shownSpeakers.reduce((sum, sp) => sum + sp.uncoveredSeconds, 0),
  }), [shownSpeakers])

  /** Jump back to the editor and locate the blind spot on its timeline. */
  const locate = (spot) => {
    setActiveKey(`${spot.speaker}|${spot.start}|${spot.end}`)
    navigate(`/projects/${projectId}?from=coverage`
      + `&focusStart=${spot.start}&focusEnd=${spot.end}`)
  }

  if (!report && !error) return <div className="page">加载中…</div>

  const summary = report?.summary

  return (
    <div className="page coverage-page">
      <div className="page-head">
        <div className="title-line">
          <Link to={`/projects/${projectId}`} className="back">
            ← 返回校注
          </Link>
          <h2>校注覆盖盲区 · {report?.projectName || ''}</h2>
        </div>
        <div className="head-actions">
          <Link className="btn" to={`/projects/${projectId}`}>
            打开时间轴校注
          </Link>
        </div>
      </div>
      {error && <div className="error">{error}</div>}

      {report && (
        <>
          <div className="panel">
            <div className="muted small coverage-hint">
              基于<strong>已保存</strong>的转写片段与校注，按半开区间
              <code>[start, end)</code> 统计：同一说话人重叠或相接的片段先合并；
              仅同名说话人的校注可覆盖其发言，校注超出发言的部分不计入，
              重叠校注不重复计时；多人同时发言分别计入各自说话人。
            </div>
            <div className="stats-grid coverage-summary">
              <div className="stat-box">
                <span className="stat-num">{summary.speakerCount}</span>
                <span className="muted small">说话人数</span>
              </div>
              <div className="stat-box">
                <span className="stat-num">
                  {fmtSeconds(summary.speechSeconds)}
                  <span className="stat-unit">s</span>
                </span>
                <span className="muted small">发言总时长</span>
              </div>
              <div className="stat-box">
                <span className="stat-num">
                  {fmtSeconds(summary.coveredSeconds)}
                  <span className="stat-unit">s</span>
                </span>
                <span className="muted small">已覆盖时长</span>
              </div>
              <div className="stat-box">
                <span className="stat-num">{fmtPct(summary.coverageRate)}</span>
                <span className="muted small">总覆盖率</span>
              </div>
              <div className="stat-box">
                <span className="stat-num">{summary.blindSpotCount}</span>
                <span className="muted small">盲区区间数</span>
              </div>
            </div>
          </div>

          {speakers.length === 0 ? (
            <div className="panel empty-hint">
              暂无可统计的发言片段（已忽略空说话人与零长度片段）。
            </div>
          ) : (
            <>
              <div className="panel">
                <h3>🎙️ 按说话人统计</h3>
                <table className="run-table coverage-table">
                  <thead>
                    <tr>
                      <th>说话人</th>
                      <th>发言时长</th>
                      <th>已覆盖</th>
                      <th>未覆盖</th>
                      <th className="coverage-rate-col">覆盖率</th>
                      <th>盲区区间</th>
                      <th>片段 / 校注</th>
                    </tr>
                  </thead>
                  <tbody>
                    {speakers.map((sp) => (
                      <tr
                        key={sp.speaker}
                        className={speakerFilter === sp.speaker ? 'selected' : ''}
                        onClick={() => setSpeakerFilter(
                          speakerFilter === sp.speaker ? '' : sp.speaker)}
                        title="点击筛选该说话人的盲区"
                      >
                        <td><strong>{sp.speaker}</strong></td>
                        <td className="cov-num">
                          {fmtSeconds(sp.speechSeconds)} s
                        </td>
                        <td className="cov-num">
                          {fmtSeconds(sp.coveredSeconds)} s
                        </td>
                        <td className="cov-num">
                          {fmtSeconds(sp.uncoveredSeconds)} s
                        </td>
                        <td className="coverage-rate-col">
                          <div className="coverage-rate">
                            <div className="coverage-bar">
                              <div
                                className="coverage-bar-fill"
                                style={{
                                  width: `${Math.min(100, sp.coverageRate * 100)}%`,
                                }}
                              />
                            </div>
                            <span className="cov-num">
                              {fmtPct(sp.coverageRate)}
                            </span>
                          </div>
                        </td>
                        <td className="cov-num">{sp.blindSpots.length}</td>
                        <td className="cov-num muted">
                          {sp.segmentCount} / {sp.annotationCount}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="panel coverage-filter-panel">
                <span className="muted small">按说话人筛选盲区：</span>
                <button
                  className={`filter-chip ${speakerFilter === '' ? 'on' : ''}`}
                  onClick={() => setSpeakerFilter('')}
                >
                  全部（{speakers.reduce((n, sp) => n + sp.blindSpots.length, 0)}）
                </button>
                {speakers.map((sp) => (
                  <button
                    key={sp.speaker}
                    className={`filter-chip ${
                      speakerFilter === sp.speaker ? 'on' : ''}`}
                    onClick={() => setSpeakerFilter(
                      speakerFilter === sp.speaker ? '' : sp.speaker)}
                  >
                    {sp.speaker}（{sp.blindSpots.length}）
                  </button>
                ))}
                <span className="muted small coverage-filter-count">
                  显示 {blindSpots.length} 个盲区 · 未覆盖{' '}
                  {fmtSeconds(totals.blind)} s / 发言 {fmtSeconds(totals.speech)} s
                </span>
              </div>

              <div className="panel">
                <h3>🕳️ 未覆盖的发言区间（{blindSpots.length}）</h3>
                {blindSpots.length === 0 ? (
                  <div className="empty-hint">
                    🎉 没有盲区：当前筛选范围内的发言已被同名校注全部覆盖。
                  </div>
                ) : (
                  <div className="speaking-interval-list">
                    {blindSpots.map((spot) => {
                      const key = `${spot.speaker}|${spot.start}|${spot.end}`
                      return (
                        <button
                          type="button"
                          key={key}
                          className={`speaking-interval coverage-spot${
                            activeKey === key ? ' active' : ''}`}
                          onClick={() => locate(spot)}
                          title="点击返回编辑页并在时间轴定位"
                        >
                          <span className="speaking-interval-time">
                            {fmtTime(spot.start)} – {fmtTime(spot.end)}
                          </span>
                          <span className="speaking-interval-speakers">
                            {spot.speaker}
                          </span>
                          <span className="speaking-interval-meta">
                            <span className="tag danger">盲区</span>
                            <span className="muted">
                              {fmtSeconds(spot.duration)} s
                            </span>
                            <span className="muted">→ 编辑页定位</span>
                          </span>
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

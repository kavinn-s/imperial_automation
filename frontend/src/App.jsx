import { useState, useRef } from 'react'
import './App.css'

function App() {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState(null)
  const [downloadUrl, setDownloadUrl] = useState(null)
  const [error, setError] = useState(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const [exportFormat, setExportFormat] = useState('csv')
  const [showConfig, setShowConfig] = useState(false)
  const [callType, setCallType] = useState('inbound')
  const [showAudit, setShowAudit] = useState(false)
  
  // Formula Config States
  const [humanIncrementSize, setHumanIncrementSize] = useState(3.0)
  const [humanIncrementCost, setHumanIncrementCost] = useState(0.15)
  const [aiFreeThreshold, setAiFreeThreshold] = useState(0.25)
  const [aiFirstLimit, setAiFirstLimit] = useState(3.0)
  const [aiFirstCost, setAiFirstCost] = useState(0.75)
  const [aiSubsequentSize, setAiSubsequentSize] = useState(3.0)
  const [aiSubsequentCost, setAiSubsequentCost] = useState(0.75)

  // Outbound Config States
  const [outboundHumanFreeThreshold, setOutboundHumanFreeThreshold] = useState(0.25)
  const [outboundHumanFirstLimit, setOutboundHumanFirstLimit] = useState(3.0)
  const [outboundHumanFirstCost, setOutboundHumanFirstCost] = useState(0.75)
  const [outboundHumanSubsequentSize, setOutboundHumanSubsequentSize] = useState(3.0)
  const [outboundHumanSubsequentCost, setOutboundHumanSubsequentCost] = useState(0.75)
  const [outboundVoicemailDroppedCost, setOutboundVoicemailDroppedCost] = useState(0.25)
  
  const fileInputRef = useRef(null)

  const handleDragOver = (e) => {
    e.preventDefault()
    setIsDragOver(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    setIsDragOver(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setIsDragOver(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndSetFile(e.dataTransfer.files[0])
    }
  }

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndSetFile(e.target.files[0])
    }
  }

  const validateAndSetFile = (selectedFile) => {
    const ext = selectedFile.name.split('.').pop().toLowerCase()
    if (ext === 'csv' || ext === 'xlsx' || ext === 'xls') {
      setFile(selectedFile)
      setError(null)
    } else {
      setError("Please select a valid CSV or Excel file.")
    }
  }

  const processFile = async () => {
    if (!file) return

    setLoading(true)
    setError(null)
    
    const formData = new FormData()
    formData.append('file', file)
    formData.append('format', exportFormat)
    formData.append('callType', callType)
    
    // Inbound
    formData.append('humanIncrementSize', humanIncrementSize)
    formData.append('humanIncrementCost', humanIncrementCost)
    formData.append('aiFreeThreshold', aiFreeThreshold)
    formData.append('aiFirstLimit', aiFirstLimit)
    formData.append('aiFirstCost', aiFirstCost)
    formData.append('aiSubsequentSize', aiSubsequentSize)
    formData.append('aiSubsequentCost', aiSubsequentCost)

    // Outbound
    formData.append('outboundHumanFreeThreshold', outboundHumanFreeThreshold)
    formData.append('outboundHumanFirstLimit', outboundHumanFirstLimit)
    formData.append('outboundHumanFirstCost', outboundHumanFirstCost)
    formData.append('outboundHumanSubsequentSize', outboundHumanSubsequentSize)
    formData.append('outboundHumanSubsequentCost', outboundHumanSubsequentCost)
    formData.append('outboundVoicemailDroppedCost', outboundVoicemailDroppedCost)

    try {
      // Use environment variable for backend URL (defaults to localhost for local dev if not set)
      let baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      if (baseUrl.endsWith('/')) baseUrl = baseUrl.slice(0, -1);
      
      const response = await fetch(`${baseUrl}/upload`, {
        method: 'POST',
        body: formData
      })

      const data = await response.json()

      if (response.ok) {
        setStats(data.stats)
        setDownloadUrl(`${baseUrl}${data.download_url}`)
      } else {
        throw new Error(data.error || 'Failed to process file')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setFile(null)
    setStats(null)
    setDownloadUrl(null)
    setError(null)
    setShowAudit(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div className="app-wrapper fade-in">
      <header className="navbar">
        <div className="container nav-content">
          <div className="logo">Voxy<span>Sync</span></div>
          <nav>
            <a href="#">Home</a>
            <a href="#">Tools</a>
            <a href="#">Privacy</a>
          </nav>
        </div>
      </header>

      <main className="main-content">
        <section className="hero slide-up">
          <h1>Process Call Data</h1>
          <p className="subtitle">Clean, standardize, and calculate billing automatically. 100% Secure & Local.</p>
          
          <div className="mode-toggle">
            <button 
              className={`mode-btn ${callType === 'inbound' ? 'active' : ''}`}
              onClick={() => { setCallType('inbound'); reset(); }}
            >
              Inbound Calls
            </button>
            <button 
              className={`mode-btn ${callType === 'outbound' ? 'active' : ''}`}
              onClick={() => { setCallType('outbound'); reset(); }}
            >
              Outbound Calls
            </button>
          </div>
        </section>

        {!stats && !loading && (
          <section className="upload-container scale-in">
            <div 
              className={`drop-zone ${isDragOver ? 'dragover' : ''}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <div className="icon">📄</div>
              <h2>Select your raw export</h2>
              <p>or drop CSV / Excel files here</p>
              
              <button className="select-btn" onClick={() => fileInputRef.current.click()}>
                Select file
              </button>
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleFileChange} 
                accept=".csv, .xlsx, .xls"
                style={{display: 'none'}} 
              />

              {file && (
                <div className="selected-file-wrapper slide-up">
                  <div className="selected-file">
                    <span>Selected: <strong>{file.name}</strong></span>
                  </div>
                  
                  <div className="format-selector">
                    <p>Export Format:</p>
                    <div className="format-options">
                      <label className={`format-radio ${exportFormat === 'csv' ? 'active' : ''}`}>
                        <input type="radio" name="format" value="csv" checked={exportFormat === 'csv'} onChange={() => setExportFormat('csv')} />
                        CSV
                      </label>
                      <label className={`format-radio ${exportFormat === 'xlsx' ? 'active' : ''}`}>
                        <input type="radio" name="format" value="xlsx" checked={exportFormat === 'xlsx'} onChange={() => setExportFormat('xlsx')} />
                        Excel
                      </label>
                      <label className={`format-radio ${exportFormat === 'pdf' ? 'active' : ''}`}>
                        <input type="radio" name="format" value="pdf" checked={exportFormat === 'pdf'} onChange={() => setExportFormat('pdf')} />
                        PDF
                      </label>
                    </div>
                  </div>

                  <button className="process-btn fancy-btn" onClick={processFile}>Process Now</button>
                </div>
              )}
              {error && <div className="error-message slide-up">{error}</div>}
            </div>
            
            <div className="config-section fade-in">
              <button 
                className="config-toggle-btn"
                onClick={() => setShowConfig(!showConfig)}
              >
                ⚙️ {showConfig ? 'Hide Billing Settings' : 'Configure Billing Formulas'}
              </button>
              
              {showConfig && (
                <div className="config-panel slide-up">
                  {callType === 'inbound' ? (
                    <>
                      <div className="config-group">
                        <h4>🧑‍💻 Human Calls (Inbound)</h4>
                        <div className="config-grid">
                          <div className="input-group">
                            <label>Increment Size (mins)</label>
                            <input type="number" step="0.1" value={humanIncrementSize} onChange={(e) => setHumanIncrementSize(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>Increment Cost ($)</label>
                            <input type="number" step="0.01" value={humanIncrementCost} onChange={(e) => setHumanIncrementCost(e.target.value)} />
                          </div>
                        </div>
                      </div>

                      <div className="config-group">
                        <h4>🤖 AI Calls (Inbound)</h4>
                        <div className="config-grid">
                          <div className="input-group">
                            <label>Free Threshold (mins)</label>
                            <input type="number" step="0.01" value={aiFreeThreshold} onChange={(e) => setAiFreeThreshold(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>First Increment Limit (mins)</label>
                            <input type="number" step="0.1" value={aiFirstLimit} onChange={(e) => setAiFirstLimit(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>First Increment Cost ($)</label>
                            <input type="number" step="0.01" value={aiFirstCost} onChange={(e) => setAiFirstCost(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>Subsequent Size (mins)</label>
                            <input type="number" step="0.1" value={aiSubsequentSize} onChange={(e) => setAiSubsequentSize(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>Subsequent Cost ($)</label>
                            <input type="number" step="0.01" value={aiSubsequentCost} onChange={(e) => setAiSubsequentCost(e.target.value)} />
                          </div>
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="config-group">
                        <h4>🗣️ Human Answered (Outbound)</h4>
                        <div className="config-grid">
                          <div className="input-group">
                            <label>Free Threshold (mins)</label>
                            <input type="number" step="0.01" value={outboundHumanFreeThreshold} onChange={(e) => setOutboundHumanFreeThreshold(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>First Increment Limit (mins)</label>
                            <input type="number" step="0.1" value={outboundHumanFirstLimit} onChange={(e) => setOutboundHumanFirstLimit(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>First Increment Cost ($)</label>
                            <input type="number" step="0.01" value={outboundHumanFirstCost} onChange={(e) => setOutboundHumanFirstCost(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>Subsequent Size (mins)</label>
                            <input type="number" step="0.1" value={outboundHumanSubsequentSize} onChange={(e) => setOutboundHumanSubsequentSize(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>Subsequent Cost ($)</label>
                            <input type="number" step="0.01" value={outboundHumanSubsequentCost} onChange={(e) => setOutboundHumanSubsequentCost(e.target.value)} />
                          </div>
                        </div>
                      </div>
                      
                      <div className="config-group">
                        <h4>📥 Voicemail (Outbound)</h4>
                        <div className="config-grid">
                          <div className="input-group">
                            <label>Voicemail Dropped Cost ($)</label>
                            <input type="number" step="0.01" value={outboundVoicemailDroppedCost} onChange={(e) => setOutboundVoicemailDroppedCost(e.target.value)} />
                          </div>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
            
            <div className="instructions fade-in">
              <h3>How it works:</h3>
              <ol>
                <li><strong>Upload</strong> your raw {callType} call export.</li>
                <li><strong>Configure</strong> billing rules in the settings above.</li>
                <li><strong>Automate</strong> calculations and cleanup instantly.</li>
                <li><strong>Download</strong> your client-ready report in any format.</li>
              </ol>
            </div>
          </section>
        )}

        {loading && (
          <section className="loading-container fade-in">
            <div className="spinner"></div>
            <h2>Processing your data...</h2>
            <p>Running securely on your local machine.</p>
          </section>
        )}

        {stats && (
          <section className="result-container scale-in">
            <div className="success-icon slide-up">🎉</div>
            <h2 className="slide-up">Processing Complete</h2>
            <p className="subtitle slide-up">Your clean data is ready for download.</p>
                        <div className="stats-layout slide-up">
              {/* Highlight Total Billable Box */}
              <div className="stat-card highlight-card">
                <span className="stat-label">Total Billable Units</span>
                <span className="stat-num glow-text">
                  {stats.total_billable_sum !== undefined ? stats.total_billable_sum : stats.total_billable_units}
                </span>
              </div>
              
              <div className="stats-grid">
                <div className="stat-card">
                  <span className="stat-num">{stats.total_rows}</span>
                  <span className="stat-label">Total Rows</span>
                </div>
                <div className="stat-card">
                  <span className="stat-num">{stats.output_rows}</span>
                  <span className="stat-label">Processed</span>
                </div>
                
                {callType === 'inbound' ? (
                  <>
                    <div className="stat-card warning">
                      <span className="stat-num">{stats.empty_duration_rows}</span>
                      <span className="stat-label">Skipped (Empty)</span>
                    </div>
                    <div className="stat-card warning">
                      <span className="stat-num">{stats.bad_transfer_value_rows}</span>
                      <span className="stat-label">Bad Values</span>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="stat-card warning">
                      <span className="stat-num">{stats.unrecognized_status_flagged}</span>
                      <span className="stat-label">Manual Review</span>
                    </div>
                    <div className="stat-card info">
                      <span className="stat-num">{stats.status_filled_from_transcript}</span>
                      <span className="stat-label">Transcript Checked</span>
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="action-buttons slide-up">
              <a href={downloadUrl} className="download-btn fancy-btn" download>
                Download Clean File ({exportFormat.toUpperCase()})
              </a>
              <button className="reset-btn" onClick={reset}>Process Another</button>
            </div>

            {callType === 'outbound' && stats.audit_trail && stats.audit_trail.length > 0 && (
              <div className="audit-section fade-in">
                <button className="config-toggle-btn" onClick={() => setShowAudit(!showAudit)} style={{marginTop: '20px'}}>
                  🔍 {showAudit ? 'Hide Audit Trail' : 'View Audit Trail (What Changed)'}
                </button>
                
                {showAudit && (
                  <div className="audit-panel slide-up">
                    <div className="audit-summary">
                      <h4>Auto-Fill Rules Fired:</h4>
                      <ul>
                        {Object.entries(stats.audit_rules_fired || {}).map(([rule, count]) => (
                          <li key={rule}><strong>{count}</strong> filled via {rule.replace(/_/g, ' ')}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="audit-table-wrapper">
                      <table className="audit-table">
                        <thead>
                          <tr>
                            <th>Row #</th>
                            <th>Phone</th>
                            <th>Changes</th>
                            <th>Reasoning</th>
                          </tr>
                        </thead>
                        <tbody>
                          {stats.audit_trail.map((audit, i) => (
                            <tr key={i}>
                              <td>{audit.row_index}</td>
                              <td>{audit.phone}</td>
                              <td>
                                {audit.recordDuration_source !== 'original' && (
                                  <span className="audit-badge duration">Duration Auto-filled</span>
                                )}
                                {audit.callBillingType_source !== 'original' && (
                                  <span className="audit-badge status">Status Auto-classified</span>
                                )}
                              </td>
                              <td className="audit-reason">
                                {audit.recordDuration_reason && <div className="reason-text">{audit.recordDuration_reason}</div>}
                                {audit.callBillingType_reason && <div className="reason-text">{audit.callBillingType_reason}</div>}
                                
                                {audit.transcript && (
                                  <details>
                                    <summary>View Transcript Excerpt</summary>
                                    <div className="transcript-box">"{audit.transcript}"</div>
                                  </details>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>
        )}
      </main>

      <footer>
        <div className="container">
          <p>&copy; 2026 VoxySync. Runs completely locally. No data leaves your machine.</p>
        </div>
      </footer>
    </div>
  )
}

export default App

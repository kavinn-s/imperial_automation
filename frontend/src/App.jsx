import { useState, useRef } from 'react'
import './App.css'

function App() {
  const [uploadMode, setUploadMode] = useState('single') // 'single' | 'batch'
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState(null)
  const [batchResult, setBatchResult] = useState(null)
  const [downloadUrl, setDownloadUrl] = useState(null)
  const [error, setError] = useState(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const [exportFormat, setExportFormat] = useState('csv')
  const [showConfig, setShowConfig] = useState(false)
  const [callType, setCallType] = useState('inbound')
  const [showAudit, setShowAudit] = useState(false)
  
  // Formula Config States - Inbound
  const [humanIncrementSize, setHumanIncrementSize] = useState(3.0)
  const [humanIncrementCost, setHumanIncrementCost] = useState(0.15)
  const [aiFreeThreshold, setAiFreeThreshold] = useState(0.25)
  const [aiFirstLimit, setAiFirstLimit] = useState(3.0)
  const [aiFirstCost, setAiFirstCost] = useState(0.75)
  const [aiSubsequentSize, setAiSubsequentSize] = useState(3.0)
  const [aiSubsequentCost, setAiSubsequentCost] = useState(0.75)

  // Formula Config States - Outbound
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
    if (uploadMode === 'batch') {
      if (ext === 'zip') {
        setFile(selectedFile)
        setError(null)
      } else {
        setError("Please select a valid .ZIP archive containing raw exports.")
      }
    } else {
      if (ext === 'csv' || ext === 'xlsx' || ext === 'xls') {
        setFile(selectedFile)
        setError(null)
      } else {
        setError("Please select a valid CSV or Excel file.")
      }
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

  const processBatchFile = async () => {
    if (!file) return

    setLoading(true)
    setError(null)

    const formData = new FormData()
    formData.append('file', file)

    // Append current formula parameters
    formData.append('humanIncrementSize', humanIncrementSize)
    formData.append('humanIncrementCost', humanIncrementCost)
    formData.append('aiFreeThreshold', aiFreeThreshold)
    formData.append('aiFirstLimit', aiFirstLimit)
    formData.append('aiFirstCost', aiFirstCost)
    formData.append('aiSubsequentSize', aiSubsequentSize)
    formData.append('aiSubsequentCost', aiSubsequentCost)

    formData.append('outboundHumanFreeThreshold', outboundHumanFreeThreshold)
    formData.append('outboundHumanFirstLimit', outboundHumanFirstLimit)
    formData.append('outboundHumanFirstCost', outboundHumanFirstCost)
    formData.append('outboundHumanSubsequentSize', outboundHumanSubsequentSize)
    formData.append('outboundHumanSubsequentCost', outboundHumanSubsequentCost)
    formData.append('outboundVoicemailDroppedCost', outboundVoicemailDroppedCost)

    try {
      let baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      if (baseUrl.endsWith('/')) baseUrl = baseUrl.slice(0, -1);

      const response = await fetch(`${baseUrl}/upload-batch`, {
        method: 'POST',
        body: formData
      })

      const data = await response.json()

      if (response.ok) {
        setBatchResult(data)
        setDownloadUrl(`${baseUrl}${data.download_url}`)
      } else {
        throw new Error(data.error || 'Failed to process batch archive')
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
    setBatchResult(null)
    setDownloadUrl(null)
    setError(null)
    setShowAudit(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  // Calculate Batch totals
  const batchTotalRows = batchResult?.sheets?.reduce((acc, s) => acc + (s.rows || 0), 0) || 0
  const batchTotalBillable = batchResult?.sheets?.reduce((acc, s) => acc + (s.billable_sum || 0), 0) || 0

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
          
          {/* Top-Level Mode Selector: Single vs Batch */}
          <div className="main-mode-toggle">
            <button 
              className={`main-mode-btn ${uploadMode === 'single' ? 'active' : ''}`}
              onClick={() => { setUploadMode('single'); reset(); }}
            >
              📄 Single File Mode
            </button>
            <button 
              className={`main-mode-btn ${uploadMode === 'batch' ? 'active' : ''}`}
              onClick={() => { setUploadMode('batch'); reset(); }}
            >
              📦 Batch (ZIP) Multi-Sheet
            </button>
          </div>

          {/* Call Type Selector for Single File Mode */}
          {uploadMode === 'single' && (
            <div className="mode-toggle fade-in">
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
              <button 
                className={`mode-btn ${callType === 'caregap' ? 'active' : ''}`}
                onClick={() => { setCallType('caregap'); reset(); }}
              >
                Caregap
              </button>
            </div>
          )}
        </section>

        {/* Upload Container - Visible when no results and not loading */}
        {!stats && !batchResult && !loading && (
          <section className="upload-container scale-in">
            <div 
              className={`drop-zone ${isDragOver ? 'dragover' : ''}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <div className="icon">{uploadMode === 'batch' ? '📦' : '📄'}</div>
              <h2>{uploadMode === 'batch' ? 'Select your Batch ZIP archive' : 'Select your raw export'}</h2>
              <p>
                {uploadMode === 'batch' 
                  ? 'or drop a ZIP file containing exports named <Agent>_<Direction>.xlsx' 
                  : 'or drop CSV / Excel files here'}
              </p>
              
              <button className="select-btn" onClick={() => fileInputRef.current.click()}>
                {uploadMode === 'batch' ? 'Select ZIP file' : 'Select file'}
              </button>
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleFileChange} 
                accept={uploadMode === 'batch' ? '.zip' : '.csv, .xlsx, .xls'}
                style={{display: 'none'}} 
              />

              {file && (
                <div className="selected-file-wrapper slide-up">
                  <div className="selected-file">
                    <span>Selected: <strong>{file.name}</strong></span>
                  </div>
                  
                  {uploadMode === 'single' && (
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
                  )}

                  {uploadMode === 'batch' ? (
                    <button className="process-btn fancy-btn" onClick={processBatchFile}>
                      Process Batch Archive
                    </button>
                  ) : (
                    <button className="process-btn fancy-btn" onClick={processFile}>
                      Process Now
                    </button>
                  )}
                </div>
              )}
              {error && <div className="error-message slide-up">{error}</div>}
            </div>
            
            {/* Billing Configurations Accordion */}
            <div className="config-section fade-in">
              <button 
                className="config-toggle-btn"
                onClick={() => setShowConfig(!showConfig)}
              >
                ⚙️ {showConfig ? 'Hide Billing Settings' : 'Configure Billing Formulas'}
              </button>
              
              {showConfig && (
                <div className="config-panel slide-up">
                  {uploadMode === 'batch' ? (
                    <>
                      <div className="config-group">
                        <h4>🧑‍💻 Inbound Calls Rates</h4>
                        <div className="config-grid">
                          <div className="input-group">
                            <label>Human Increment Size (mins)</label>
                            <input type="number" step="0.1" value={humanIncrementSize} onChange={(e) => setHumanIncrementSize(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>Human Increment Cost ($)</label>
                            <input type="number" step="0.01" value={humanIncrementCost} onChange={(e) => setHumanIncrementCost(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>AI Free Threshold (mins)</label>
                            <input type="number" step="0.01" value={aiFreeThreshold} onChange={(e) => setAiFreeThreshold(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>AI First Increment Limit (mins)</label>
                            <input type="number" step="0.1" value={aiFirstLimit} onChange={(e) => setAiFirstLimit(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>AI First Increment Cost ($)</label>
                            <input type="number" step="0.01" value={aiFirstCost} onChange={(e) => setAiFirstCost(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>AI Subsequent Size (mins)</label>
                            <input type="number" step="0.1" value={aiSubsequentSize} onChange={(e) => setAiSubsequentSize(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>AI Subsequent Cost ($)</label>
                            <input type="number" step="0.01" value={aiSubsequentCost} onChange={(e) => setAiSubsequentCost(e.target.value)} />
                          </div>
                        </div>
                      </div>

                      <div className="config-group">
                        <h4>🗣️ Outbound Calls Rates</h4>
                        <div className="config-grid">
                          <div className="input-group">
                            <label>Human Free Threshold (mins)</label>
                            <input type="number" step="0.01" value={outboundHumanFreeThreshold} onChange={(e) => setOutboundHumanFreeThreshold(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>Human First Limit (mins)</label>
                            <input type="number" step="0.1" value={outboundHumanFirstLimit} onChange={(e) => setOutboundHumanFirstLimit(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>Human First Cost ($)</label>
                            <input type="number" step="0.01" value={outboundHumanFirstCost} onChange={(e) => setOutboundHumanFirstCost(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>Human Subsequent Size (mins)</label>
                            <input type="number" step="0.1" value={outboundHumanSubsequentSize} onChange={(e) => setOutboundHumanSubsequentSize(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>Human Subsequent Cost ($)</label>
                            <input type="number" step="0.01" value={outboundHumanSubsequentCost} onChange={(e) => setOutboundHumanSubsequentCost(e.target.value)} />
                          </div>
                          <div className="input-group">
                            <label>Voicemail Dropped Cost ($)</label>
                            <input type="number" step="0.01" value={outboundVoicemailDroppedCost} onChange={(e) => setOutboundVoicemailDroppedCost(e.target.value)} />
                          </div>
                        </div>
                      </div>
                    </>
                  ) : callType === 'caregap' ? (
                    <div className="config-group">
                      <h4>⚙️ Caregap Settings</h4>
                      <p style={{marginTop: '10px', color: '#666'}}>Caregap rules are currently hardcoded to standard specifications. No configuration needed.</p>
                    </div>
                  ) : callType === 'inbound' ? (
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
              <h3>{uploadMode === 'batch' ? 'Batch Processing Guide:' : 'How it works:'}</h3>
              {uploadMode === 'batch' ? (
                <ol>
                  <li>Package your raw exports into a <strong>.ZIP</strong> file.</li>
                  <li>Name each file as <code>&lt;AgentName&gt;_&lt;Direction&gt;.xlsx</code> (e.g. <code>Claims_Inbound.xlsx</code>, <code>TRCPF_Outbound.xlsx</code>, <code>SmartAgent_Diabetes.xlsx</code>).</li>
                  <li>Click <strong>Process Batch Archive</strong> to route and calculate every file automatically.</li>
                  <li>Download <strong>one multi-sheet Excel workbook</strong> containing all processed sheets.</li>
                </ol>
              ) : (
                <ol>
                  <li><strong>Upload</strong> your raw {callType} call export.</li>
                  <li><strong>Configure</strong> billing rules in the settings above.</li>
                  <li><strong>Automate</strong> calculations and cleanup instantly.</li>
                  <li><strong>Download</strong> your client-ready report in any format.</li>
                </ol>
              )}
            </div>
          </section>
        )}

        {/* Loading Spinner */}
        {loading && (
          <section className="loading-container fade-in">
            <div className="spinner"></div>
            <h2>{uploadMode === 'batch' ? 'Processing Batch Archive...' : 'Processing your data...'}</h2>
            <p>Running securely on your local machine.</p>
          </section>
        )}

        {/* Results for Single File Mode */}
        {stats && uploadMode === 'single' && (
          <section className="result-container scale-in">
            <div className="success-icon slide-up">🎉</div>
            <h2 className="slide-up">Processing Complete</h2>
            <p className="subtitle slide-up">Your clean data is ready for download.</p>
            
            <div className="stats-layout slide-up">
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

        {/* Results for Batch ZIP Mode */}
        {batchResult && uploadMode === 'batch' && (
          <section className="result-container scale-in">
            <div className="success-icon slide-up">🎉</div>
            <h2 className="slide-up">Batch Processing Complete</h2>
            <p className="subtitle slide-up">Combined multi-sheet Excel workbook is ready for download.</p>

            <div className="stats-layout slide-up">
              <div className="stat-card highlight-card">
                <span className="stat-label">Total Billable Units (All Sheets)</span>
                <span className="stat-num glow-text">{batchTotalBillable.toFixed(2)}</span>
              </div>
              
              <div className="stats-grid">
                <div className="stat-card">
                  <span className="stat-num">{batchResult.sheets?.length || 0}</span>
                  <span className="stat-label">Sheets Created</span>
                </div>
                <div className="stat-card">
                  <span className="stat-num">{batchTotalRows}</span>
                  <span className="stat-label">Total Rows Cleaned</span>
                </div>
                <div className="stat-card warning">
                  <span className="stat-num">{batchResult.skipped?.length || 0}</span>
                  <span className="stat-label">Files Skipped</span>
                </div>
              </div>
            </div>

            {/* Sheets Table */}
            <div className="batch-sheets-section slide-up">
              <h3>Generated Excel Sheets:</h3>
              <div className="audit-table-wrapper">
                <table className="audit-table">
                  <thead>
                    <tr>
                      <th>Sheet Name</th>
                      <th>Source File</th>
                      <th>Direction</th>
                      <th>Rows</th>
                      <th>Billable Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batchResult.sheets?.map((sheet, idx) => (
                      <tr key={idx}>
                        <td><strong>{sheet.sheet_name}</strong></td>
                        <td style={{color: 'var(--text-muted)'}}>{sheet.filename}</td>
                        <td>
                          <span className={`audit-badge ${sheet.direction === 'inbound' ? 'duration' : 'status'}`}>
                            {sheet.direction.toUpperCase()}
                          </span>
                        </td>
                        <td>{sheet.rows}</td>
                        <td><strong>${Number(sheet.billable_sum).toFixed(2)}</strong></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Skipped Files Section */}
            {batchResult.skipped && batchResult.skipped.length > 0 && (
              <div className="skipped-section slide-up">
                <h4>⚠️ Skipped Files ({batchResult.skipped.length})</h4>
                <div className="audit-table-wrapper">
                  <table className="audit-table skipped-table">
                    <thead>
                      <tr>
                        <th>Filename</th>
                        <th>Reason Skipped</th>
                      </tr>
                    </thead>
                    <tbody>
                      {batchResult.skipped.map((sk, idx) => (
                        <tr key={idx}>
                          <td><code>{sk.filename}</code></td>
                          <td className="skipped-reason">{sk.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div className="action-buttons slide-up">
              <a href={downloadUrl} className="download-btn fancy-btn" download>
                📥 Download Multi-Sheet Workbook (.XLSX)
              </a>
              <button className="reset-btn" onClick={reset}>Process Another Batch</button>
            </div>
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

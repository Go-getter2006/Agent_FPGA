// 助教对话（阶段 4 接入大模型；现在只显示外框）
export default function ChatPanel() {
  return (
    <div className="card chat" data-testid="chat-panel">
      <div className="card-h">问助教 <small>不会直接给答案</small></div>
      <div className="msgs">
        <div className="msg ai">对话功能将在接入大模型后开放。现在可以先用上面的提示阶梯。</div>
      </div>
      <div className="chat-in">
        <div className="tip">助教只给思路，不给代码</div>
        <div className="box"><input placeholder="问助教……" disabled aria-label="问助教" />
          <button className="wave-btn primary" disabled>发送</button></div>
      </div>
    </div>
  )
}

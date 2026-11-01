"""
知途 · AI 出行与消费性价比决策 Agent —— 应用入口

启动：
    python app.py
然后浏览器打开 http://127.0.0.1:5000
"""
from flask import Flask, jsonify, render_template

from config import Config
from routes import api_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.register_blueprint(api_bp)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.errorhandler(404)
    def not_found(_err):
        return jsonify({"ok": False, "error": "接口不存在"}), 404

    @app.errorhandler(500)
    def server_error(err):
        app.logger.exception("未捕获异常: %s", err)
        return jsonify({"ok": False, "error": "服务器内部错误，请查看后端日志"}), 500

    @app.after_request
    def no_cache(response):
        # 演示期间避免浏览器缓存导致前端改动不生效
        if response.mimetype in ("text/html", "application/javascript", "text/css"):
            response.headers["Cache-Control"] = "no-store"
        return response

    return app


app = create_app()


if __name__ == "__main__":
    print("=" * 62)
    print("  知途 · AI 出行与消费性价比决策 Agent")
    print(f"  访问地址:   http://{Config.HOST}:{Config.PORT}")
    print(f"  大模型:     {Config.LLM_PROVIDER}  (ready={Config.llm_ready()})")
    print(f"  搜索渠道:   {Config.SEARCH_PROVIDER}  {Config.search_ready()}")
    print("  配置自检:   http://127.0.0.1:%d/api/agent/status" % Config.PORT)
    print("=" * 62)
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)

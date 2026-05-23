"""
turtle_node.py
Nó ROS 2 que lê o arquivo path.json gerado por process_image.py
e comanda a tartaruga do turtlesim para reproduzir os contornos da imagem.

Estratégia de controle:
- Usa o serviço /turtle1/teleport_absolute para posicionar a tartaruga com precisão.
- Usa o serviço /turtle1/set_pen para controlar se a caneta está abaixada (desenhando)
  ou levantada (movendo sem desenhar).
- Quando o caminho contém None, levanta a caneta para mover para o próximo segmento.
"""

import json
import os
import threading

import rclpy
from rclpy.node import Node
from turtlesim.srv import TeleportAbsolute, SetPen
from std_srvs.srv import Empty


# Caminho padrão para o arquivo JSON (relativo ao diretório de trabalho)
DEFAULT_PATH_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', '..', '..', '..', 'path.json'
)


class TurtleDrawNode(Node):
    """
    Nó responsável por desenhar os contornos da imagem no turtlesim.

    Fluxo:
      1. Carrega o caminho do arquivo JSON.
      2. Limpa a tela do turtlesim.
      3. Percorre cada ponto do caminho:
         - None → levanta a caneta e teleporta para o próximo ponto.
         - (x, y) → teleporta com a caneta abaixada.
    """

    def __init__(self):
        super().__init__('turtle_draw_node')

        # Parâmetro: caminho do arquivo JSON
        self.declare_parameter('path_file', DEFAULT_PATH_FILE)
        path_file = self.get_parameter('path_file').get_parameter_value().string_value

        # Clientes de serviço
        self.teleport_client = self.create_client(TeleportAbsolute, '/turtle1/teleport_absolute')
        self.pen_client       = self.create_client(SetPen,           '/turtle1/set_pen')
        self.clear_client     = self.create_client(Empty,            '/clear')

        self.get_logger().info("Aguardando serviços do turtlesim...")
        self.teleport_client.wait_for_service(timeout_sec=10.0)
        self.pen_client.wait_for_service(timeout_sec=10.0)
        self.clear_client.wait_for_service(timeout_sec=10.0)
        self.get_logger().info("Serviços disponíveis. Iniciando desenho.")

        # Carrega o caminho
        self.path = self._load_path(path_file)
        if not self.path:
            self.get_logger().error(f"Caminho vazio ou arquivo não encontrado: {path_file}")
            return

        self.get_logger().info(f"Caminho carregado: {len(self.path)} entradas.")

        # Limpa o turtlesim
        self._clear_screen()

        # Começa o desenho em uma thread separada (não bloqueia o executor ROS)
        self._drawing_done = False
        threading.Thread(target=self._start_drawing, daemon=True).start()

    # ─────────────────────────────────────────────────────────
    # Métodos auxiliares
    # ─────────────────────────────────────────────────────────

    def _load_path(self, path_file: str) -> list:
        """Lê o JSON e converte para lista de tuplas ou None."""
        try:
            with open(path_file, 'r') as f:
                raw = json.load(f)
            # raw é lista de [x, y] ou null
            return [tuple(pt) if pt is not None else None for pt in raw]
        except Exception as e:
            self.get_logger().error(f"Erro ao carregar path.json: {e}")
            return []

    def _wait_for_future(self, future, timeout_sec=5.0):
        """Aguarda um futuro de forma segura fora do executor principal."""
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout_sec)

    def _clear_screen(self):
        """Chama o serviço /clear para limpar o canvas."""
        req = Empty.Request()
        future = self.clear_client.call_async(req)
        self._wait_for_future(future)

    def _teleport(self, x: float, y: float, theta: float = 0.0):
        """Teleporta a tartaruga para (x, y, theta)."""
        req = TeleportAbsolute.Request()
        req.x = float(x)
        req.y = float(y)
        req.theta = float(theta)
        future = self.teleport_client.call_async(req)
        self._wait_for_future(future)

    def _set_pen(self, r: int, g: int, b: int, width: int, off: int):
        """
        Controla a caneta da tartaruga.
        off=1 → caneta levantada (sem traço)
        off=0 → caneta abaixada (desenhando)
        """
        req = SetPen.Request()
        req.r = r
        req.g = g
        req.b = b
        req.width = width
        req.off = off
        future = self.pen_client.call_async(req)
        self._wait_for_future(future)

    # ─────────────────────────────────────────────────────────
    # Lógica de desenho
    # ─────────────────────────────────────────────────────────

    def _start_drawing(self):
        """Chamado uma vez pelo timer para iniciar o percurso."""
        if self._drawing_done:
            return
        self._drawing_done = True

        self.get_logger().info("Iniciando percurso do contorno...")

        # Levanta a caneta antes de qualquer movimento
        self._set_pen(255, 255, 255, 1, 1)  # off=1 → sem traço

        pen_down = False
        total = len(self.path)

        for i, point in enumerate(self.path):
            if i % 100 == 0:
                self.get_logger().info(f"  Progresso: {i}/{total}")

            if point is None:
                # Levanta a caneta para o próximo segmento
                self._set_pen(255, 255, 255, 1, 1)
                pen_down = False
            else:
                x, y = point
                if not pen_down:
                    # Teleporta sem desenhar até o início do segmento
                    self._teleport(x, y)
                    # Abaixa a caneta (cor branca, 1 pixel de largura)
                    self._set_pen(255, 255, 255, 1, 0)
                    pen_down = True
                else:
                    self._teleport(x, y)

        # Levanta a caneta ao finalizar
        self._set_pen(255, 255, 255, 1, 1)
        self.get_logger().info("Desenho concluído!")


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = TurtleDrawNode()
    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(node)
    executor.spin()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
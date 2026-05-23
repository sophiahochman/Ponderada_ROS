# Turtle Draw 🐢

Reproduz os contornos de uma imagem no **turtlesim** usando uma pipeline de visão computacional implementada do zero (apenas NumPy + OpenCV só para leitura).

## Estrutura

```
turtle/
├── process_image.py        # Pipeline de visão computacional
├── path.json               # Gerado automaticamente pelo script acima
├── edges_result.png        # Visualização das etapas (gerada automaticamente)
├── image/
│   └── input.jpg           # ← coloque sua imagem aqui
└── turtle_draw/            # Pacote ROS 2
    ├── package.xml
    ├── setup.py
    ├── setup.cfg
    ├── resource/turtle_draw
    └── turtle_draw/
        ├── __init__.py
        └── turtle_node.py
```

## Dependências

```bash
pip install numpy opencv-python matplotlib
```

> ROS 2 (Humble ou Jazzy) com o pacote `turtlesim` instalado.

## Como executar

### 1. Gerar o caminho a partir da imagem

Coloque a imagem em `image/input.jpg` (ou passe o caminho como argumento):

```bash
cd /caminho/para/turtle
python3 process_image.py image/input.jpg
```

Isso gera `path.json` e abre a visualização das etapas da pipeline.

### 2. Construir o pacote ROS 2

```bash
# A partir do workspace ROS 2 (copie a pasta turtle_draw para o src/)
cd ~/ros2_ws
cp -r /caminho/para/turtle/turtle_draw src/
colcon build --packages-select turtle_draw
source install/setup.bash
```

### 3. Iniciar o turtlesim

```bash
# Terminal 1
ros2 run turtlesim turtlesim_node
```

### 4. Rodar o nó de desenho

```bash
# Terminal 2
ros2 run turtle_draw turtle_node --ros-args -p path_file:=/caminho/absoluto/para/path.json
```

A tartaruga percorrerá automaticamente todos os contornos da imagem.

## Pipeline de Visão Computacional

| Etapa | Método | Justificativa |
|-------|--------|---------------|
| Escala de cinza | Fórmula de luminância `Y = 0.114B + 0.587G + 0.299R` | Simula sensibilidade do olho humano |
| Resize | Nearest-neighbor para 200×200 | Reduz pontos mantendo estrutura |
| Suavização | Gaussiana 5×5, σ=1.4 | Remove ruído antes de derivar |
| Gradientes | Operador de Sobel (Gx, Gy) | Aproxima derivada discreta da imagem |
| Afinar bordas | Supressão de não-máximos | Deixa bordas com 1 pixel de espessura |
| Limiares | Limiar duplo (5% / 15% do máximo) | Diferencia bordas fortes de fracas |
| Histerese | Conectividade 8-vizinhos | Elimina bordas falsas isoladas |
| Caminho | Greedy nearest-neighbor | Minimiza saltos entre pontos de borda |

## Controle ROS 2

- **`/turtle1/teleport_absolute`** — posiciona a tartaruga com precisão (x, y, θ).  
- **`/turtle1/set_pen`** — levanta (`off=1`) ou abaixa (`off=0`) a caneta.  
- Quando o caminho contém `null` (None), a caneta é levantada e a tartaruga salta para o próximo segmento de contorno.

---

## Relatório Técnico — Turtle Draw

### 1. Introdução

O objetivo desta atividade foi construir uma pipeline completa de visão computacional — sem uso de bibliotecas prontas de processamento de imagem — e integrá-la a um pacote ROS 2 que controla a tartaruga do turtlesim para reproduzir os contornos detectados.

A imagem utilizada foi uma fotografia de um bulldog francês, escolhida por possuir bordas bem definidas (orelhas, contorno da cabeça, olhos) e contraste razoável entre o sujeito e o fundo.

---

### 2. Pipeline de Visão Computacional (`process_image.py`)

#### 2.1 Carregamento e conversão para escala de cinza

O único uso permitido de OpenCV foi `cv2.imread`, que carrega a imagem em formato BGR. A conversão para escala de cinza foi feita manualmente com a fórmula de luminância perceptual:

$$Y = 0{,}114 \cdot B + 0{,}587 \cdot G + 0{,}299 \cdot R$$

Essa ponderação reflete a sensibilidade do olho humano: o verde é o canal mais percebido, seguido do vermelho e do azul.

#### 2.2 Redimensionamento

A imagem foi redimensionada para **200×200 pixels** usando interpolação nearest-neighbor implementada manualmente com índices NumPy. A escolha de 200×200 equilibra detalhe dos contornos e quantidade de pontos de caminho (evitando percursos muito longos no turtlesim).

#### 2.3 Suavização gaussiana

Um filtro gaussiano **5×5 com σ = 1,4** foi aplicado antes da detecção de bordas. O objetivo é atenuar ruídos de alta frequência que, sem suavização, seriam detectados como bordas falsas pelo operador de Sobel.

A convolução foi implementada sem loops pixel a pixel: iterou-se sobre os **kh × kw = 25** elementos do kernel e somou-se shifts vetorizados do array, mantendo boa performance com NumPy puro.

#### 2.4 Detecção de bordas (Canny simplificado)

A detecção seguiu as etapas clássicas do algoritmo de Canny:

1. **Gradientes de Sobel**: Os kernels 3×3 de Sobel foram aplicados para calcular os gradientes $G_x$ e $G_y$. A magnitude $|G| = \sqrt{G_x^2 + G_y^2}$ indica a força da borda, e o ângulo $\theta = \text{atan2}(G_y, G_x)$ indica sua direção.

2. **Supressão de não-máximos (NMS)**: Para cada pixel, verifica-se se ele é o máximo local na direção do gradiente (quantizada em 0°, 45°, 90°, 135°). Isso afina as bordas para espessura de 1 pixel, evitando bordas espessas e imprecisas.

3. **Limiar duplo**: Um limiar alto (15% do máximo) marca bordas fortes; um limiar baixo (5%) marca bordas fracas candidatas.

4. **Histerese**: Pixels fracos adjacentes (8-conectividade) a pixels fortes são aceitos como borda; os demais são descartados. Isso conecta bordas fragmentadas e elimina falsos positivos isolados.

**Justificativa das escolhas**: O Canny é o detector de bordas mais utilizado na prática por seu bom equilíbrio entre sensibilidade e robustez ao ruído. A implementação do zero demonstra compreensão de cada componente.

---

### 3. Planejamento de Caminho

Os pixels de borda detectados (valor 255) foram extraídos como coordenadas `(row, col)` e ordenados por um algoritmo **greedy nearest-neighbor**: parte-se de um ponto qualquer e sempre avança para o vizinho não-visitado mais próximo. Quando a distância ao próximo ponto supera um limiar (`max_gap = 5.0` pixels), insere-se um `None` na lista, sinalizando que a caneta deve ser levantada.

O mapeamento para o espaço do turtlesim foi feito de forma linear:

$$x_{ts} = 1{,}0 + \frac{col}{199} \cdot 9{,}0 \qquad y_{ts} = 10{,}0 - \frac{row}{199} \cdot 9{,}0$$

O eixo Y é invertido porque pixels têm a origem no canto superior esquerdo, enquanto o turtlesim usa a origem no canto inferior esquerdo.

---

### 4. Pacote ROS 2 (`turtle_draw`)

O nó `TurtleDrawNode` utiliza dois serviços:

- **`/turtle1/teleport_absolute`**: Posiciona a tartaruga com precisão em (x, y). Optou-se por teleporte em vez de comandos de velocidade para garantir que cada ponto do contorno seja reproduzido fielmente, sem acúmulo de erro de integração.

- **`/turtle1/set_pen`**: Controla a caneta (`off=0` para desenhar, `off=1` para mover sem traço). Toda vez que o caminho contém `None`, a caneta é levantada e a tartaruga move-se para o início do próximo segmento sem deixar traço.

O caminho é fornecido via arquivo `path.json` (gerado pela etapa anterior), passado como parâmetro ROS 2 (`path_file`), o que desacopla o processamento de imagem do controle do robô.

---

### 5. Dificuldades Encontradas

- **Performance da convolução**: A convolução pixel a pixel é inviável em Python puro para imagens grandes. Resolvi iterando sobre o kernel (25 operações matriciais) em vez de cada pixel, reduzindo drasticamente o tempo.
- **Ordenação do caminho**: O greedy nearest-neighbor em O(n²) é lento para muitos pontos. Reduzir a imagem para 200×200 manteve o número de pontos abaixo de ~2000, tornando a ordenação aceitável (~2s).
- **Histerese com loops**: A histerese exige iterar pixel a pixel; para 200×200 isso representa 40.000 iterações Python — aceitável mas lento (alguns segundos). Uma solução seria usar morfologia com NumPy, mas fugiria da implementação manual.


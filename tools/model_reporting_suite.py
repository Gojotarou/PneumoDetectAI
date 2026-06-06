import argparse
import json
from pathlib import Path

import matplotlib.cm as cm
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from PIL import Image
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    auc,
    classification_report,
    confusion_matrix,
    roc_curve,
)
from tensorflow.keras.models import load_model


PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGE_SIZE = (224, 224)
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "pneumonia_model.h5"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "report_outputs"


def load_test_dataset(test_dir, batch_size):
    raw_dataset = tf.keras.utils.image_dataset_from_directory(
        test_dir,
        labels="inferred",
        label_mode="int",
        color_mode="rgb",
        image_size=IMAGE_SIZE,
        batch_size=batch_size,
        shuffle=False,
    )
    class_names = raw_dataset.class_names
    normalized_dataset = raw_dataset.map(
        lambda images, labels: (tf.cast(images, tf.float32) / 255.0, labels)
    )
    return raw_dataset, normalized_dataset, class_names


def collect_true_labels(raw_dataset):
    y_true = []
    for _, labels in raw_dataset:
        y_true.extend(labels.numpy().astype(int).ravel())
    return np.asarray(y_true)


def get_pred_scores_and_labels(predictions, threshold):
    predictions = np.asarray(predictions)

    # Multi-output model (e.g., [normal_prob, pneumonia_prob]).
    if predictions.ndim == 2 and predictions.shape[1] > 1:
        y_scores = predictions[:, 1]
        y_pred = np.argmax(predictions, axis=1)
        return y_scores, y_pred

    # Single-output sigmoid model.
    y_scores = predictions.ravel()
    y_pred = (y_scores >= threshold).astype(int)
    return y_scores, y_pred


def save_confusion_matrix(y_true, y_pred, class_names, output_png):
    labels = list(range(len(class_names)))
    cmatrix = confusion_matrix(y_true, y_pred, labels=labels)

    fig, ax = plt.subplots(figsize=(7, 6), dpi=150)
    disp = ConfusionMatrixDisplay(confusion_matrix=cmatrix, display_labels=class_names)
    disp.plot(ax=ax, cmap="Blues", values_format="d", colorbar=False)
    ax.set_title("Pneumonia Model Confusion Matrix")
    ax.set_xlabel("Predicted Label")
    ax.set_ylabel("True Label")
    plt.xticks(rotation=15)
    plt.tight_layout()
    plt.savefig(output_png, format="png", bbox_inches="tight")
    plt.close(fig)


def save_classification_report(y_true, y_pred, class_names, output_txt):
    labels = list(range(len(class_names)))
    report = classification_report(
        y_true,
        y_pred,
        labels=labels,
        target_names=class_names,
        digits=4,
    )
    accuracy = accuracy_score(y_true, y_pred)
    mapping_lines = [f"  {idx} -> {name}" for idx, name in enumerate(class_names)]

    text = (
        "Pneumonia Classification Report\n"
        + "=" * 40
        + "\n\nLabel Mapping\n"
        + "-" * 13
        + "\n"
        + "\n".join(mapping_lines)
        + "\n\nClassification Report\n"
        + "-" * 21
        + "\n"
        + report
        + f"\nOverall Accuracy: {accuracy:.4f}\n"
    )

    output_txt.write_text(text, encoding="utf-8")
    print(text)


def save_roc_auc(y_true, y_scores, output_png):
    fpr, tpr, _ = roc_curve(y_true, y_scores)
    auc_score = auc(fpr, tpr)

    fig, ax = plt.subplots(figsize=(7, 6), dpi=150)
    ax.plot(fpr, tpr, color="darkorange", linewidth=2, label=f"ROC curve (AUC = {auc_score:.4f})")
    ax.plot([0, 1], [0, 1], color="navy", linewidth=1.5, linestyle="--", label="Random baseline")
    ax.set_title("ROC Curve - Pneumonia Classification")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(output_png, format="png", bbox_inches="tight")
    plt.close(fig)

    return auc_score


def load_history_dict(history_json_path):
    raw = json.loads(history_json_path.read_text(encoding="utf-8"))

    if isinstance(raw, dict) and "history" in raw and isinstance(raw["history"], dict):
        return raw["history"]
    if isinstance(raw, dict):
        return raw
    raise ValueError("History JSON must be a dict or contain a top-level 'history' dict.")


def save_training_history_plot(history_dict, output_png):
    train_acc = history_dict.get("accuracy", [])
    val_acc = history_dict.get("val_accuracy", [])
    train_loss = history_dict.get("loss", [])
    val_loss = history_dict.get("val_loss", [])

    if not (train_acc or val_acc or train_loss or val_loss):
        raise ValueError("No accuracy/loss values found in history.")

    epochs = range(1, max(len(train_acc), len(val_acc), len(train_loss), len(val_loss)) + 1)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), dpi=150)

    if train_acc:
        axes[0].plot(range(1, len(train_acc) + 1), train_acc, label="Train Accuracy", linewidth=2)
    if val_acc:
        axes[0].plot(range(1, len(val_acc) + 1), val_acc, label="Validation Accuracy", linewidth=2)
    axes[0].set_title("Training vs Validation Accuracy")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Accuracy")
    axes[0].set_xticks(list(epochs))
    axes[0].grid(alpha=0.25)
    axes[0].legend()

    if train_loss:
        axes[1].plot(range(1, len(train_loss) + 1), train_loss, label="Train Loss", linewidth=2)
    if val_loss:
        axes[1].plot(range(1, len(val_loss) + 1), val_loss, label="Validation Loss", linewidth=2)
    axes[1].set_title("Training vs Validation Loss")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Loss")
    axes[1].set_xticks(list(epochs))
    axes[1].grid(alpha=0.25)
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(output_png, format="png", bbox_inches="tight")
    plt.close(fig)


def _iter_all_layers(model):
    # Recursively flatten nested models so Grad-CAM can find conv layers inside wrappers.
    return [
        layer
        for layer in model._flatten_layers(include_self=False, recursive=True)
        if not isinstance(layer, tf.keras.Model)
    ]


def _layer_looks_like_conv_feature_map(layer):
    # Keras 3 may not always expose output_shape; inspect symbolic output shape too.
    output_shape = getattr(layer, "output_shape", None)
    if output_shape is not None:
        try:
            if len(output_shape) == 4:
                return True
        except TypeError:
            pass

    layer_output = getattr(layer, "output", None)
    if layer_output is not None:
        shape = getattr(layer_output, "shape", None)
        rank = getattr(shape, "rank", None)
        if rank == 4:
            return True
        try:
            if shape is not None and len(shape) == 4:
                return True
        except TypeError:
            pass

    class_name = layer.__class__.__name__.lower()
    if "conv" in class_name:
        return True

    return False


def resolve_conv_layer(model, conv_layer_name=None):
    all_layers = _iter_all_layers(model)

    if conv_layer_name:
        for layer in all_layers:
            if layer.name == conv_layer_name:
                return layer
        raise ValueError(
            f"Grad-CAM layer '{conv_layer_name}' was not found. "
            "Use --gradcam-layer with a valid layer name from model.summary()."
        )

    for layer in reversed(all_layers):
        if _layer_looks_like_conv_feature_map(layer):
            return layer

    # Provide a short list of candidate layer names to make manual override easy.
    candidates = []
    for layer in all_layers:
        layer_output = getattr(layer, "output", None)
        shape = getattr(layer_output, "shape", None)
        rank = getattr(shape, "rank", None)
        if rank == 4 or "conv" in layer.__class__.__name__.lower():
            candidates.append(layer.name)

    hint = ""
    if candidates:
        sample = ", ".join(candidates[-10:])
        hint = f" Candidate layers: {sample}"

    raise ValueError(
        "Could not find a convolutional feature map layer for Grad-CAM. "
        "Try --gradcam-layer with one of your model layer names."
        + hint
    )


def preprocess_single_image(image_path):
    image = Image.open(image_path).convert("RGB")
    image = image.resize(IMAGE_SIZE)
    array = np.array(image, dtype=np.float32) / 255.0
    batch = np.expand_dims(array, axis=0)
    return array, batch


def build_gradcam_heatmap(model, image_batch, conv_layer, pred_index=None):
    grad_model = tf.keras.models.Model(
        inputs=model.inputs,
        outputs=[conv_layer.output, model.output],
    )

    with tf.GradientTape() as tape:
        conv_outputs, preds = grad_model(image_batch)
        if pred_index is None:
            pred_index = tf.argmax(preds[0])
        class_channel = preds[:, pred_index]

    grads = tape.gradient(class_channel, conv_outputs)
    pooled_grads = tf.reduce_mean(grads, axis=(0, 1, 2))
    conv_outputs = conv_outputs[0]

    heatmap = tf.reduce_sum(conv_outputs * pooled_grads, axis=-1)
    heatmap = tf.maximum(heatmap, 0)
    max_val = tf.math.reduce_max(heatmap)
    if float(max_val) > 0:
        heatmap = heatmap / max_val
    heatmap = heatmap.numpy()
    return heatmap


def save_gradcam_figure(model, image_path, class_names, output_png, conv_layer_name=None, alpha=0.4):
    original_img, image_batch = preprocess_single_image(image_path)

    preds = model.predict(image_batch, verbose=0)
    if preds.ndim == 2 and preds.shape[1] > 1:
        pred_idx = int(np.argmax(preds[0]))
        pred_score = float(preds[0][pred_idx])
    else:
        pred_score = float(preds.ravel()[0])
        pred_idx = 1 if pred_score >= 0.5 else 0

    conv_layer = resolve_conv_layer(model, conv_layer_name)

    heatmap = build_gradcam_heatmap(model, image_batch, conv_layer, pred_index=pred_idx)
    heatmap_uint8 = np.uint8(255 * heatmap)
    color_map = cm.get_cmap("jet")
    color_heatmap = color_map(heatmap_uint8)[:, :, :3]

    resized_heatmap = tf.image.resize(
        np.expand_dims(color_heatmap, axis=0),
        IMAGE_SIZE,
    ).numpy()[0]

    overlay = np.clip((1 - alpha) * original_img + alpha * resized_heatmap, 0, 1)

    pred_label = class_names[pred_idx] if pred_idx < len(class_names) else str(pred_idx)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), dpi=150)
    axes[0].imshow(original_img)
    axes[0].set_title("Original Image")
    axes[0].axis("off")

    axes[1].imshow(heatmap, cmap="jet")
    axes[1].set_title("Grad-CAM Heatmap")
    axes[1].axis("off")

    axes[2].imshow(overlay)
    axes[2].set_title(f"Overlay | Pred: {pred_label} ({pred_score:.4f})")
    axes[2].axis("off")

    plt.tight_layout()
    plt.savefig(output_png, format="png", bbox_inches="tight")
    plt.close(fig)


def run_full_report(
    model_path,
    test_dir,
    output_dir,
    batch_size,
    threshold,
    history_json,
    gradcam_image,
    gradcam_layer,
):
    output_dir.mkdir(parents=True, exist_ok=True)

    model = load_model(model_path)
    raw_dataset, normalized_dataset, class_names = load_test_dataset(test_dir, batch_size)

    y_true = collect_true_labels(raw_dataset)
    predictions = model.predict(normalized_dataset, verbose=1)
    y_scores, y_pred = get_pred_scores_and_labels(predictions, threshold)

    print("Detected class mapping from test folder:")
    for idx, name in enumerate(class_names):
        print(f"  {idx} -> {name}")

    cm_path = output_dir / "pneumonia_confusion_matrix.png"
    report_path = output_dir / "pneumonia_classification_report.txt"
    roc_path = output_dir / "pneumonia_roc_curve.png"

    save_confusion_matrix(y_true, y_pred, class_names, cm_path)
    save_classification_report(y_true, y_pred, class_names, report_path)
    auc_score = save_roc_auc(y_true, y_scores, roc_path)
    print(f"ROC AUC: {auc_score:.4f}")

    if history_json:
        history_path = Path(history_json)
        history_dict = load_history_dict(history_path)
        history_png = output_dir / "training_history_curves.png"
        save_training_history_plot(history_dict, history_png)
        print(f"Saved training history curves: {history_png}")
    else:
        print("Skipped training history plot (no --history-json provided).")

    if gradcam_image:
        gradcam_png = output_dir / "gradcam_visualization.png"
        save_gradcam_figure(
            model=model,
            image_path=Path(gradcam_image),
            class_names=class_names,
            output_png=gradcam_png,
            conv_layer_name=gradcam_layer,
        )
        print(f"Saved Grad-CAM visualization: {gradcam_png}")
    else:
        print("Skipped Grad-CAM (no --gradcam-image provided).")

    print("\nGenerated report files:")
    for path in sorted(output_dir.glob("*")):
        print(f"- {path}")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Generate pneumonia model reporting artifacts in one run."
    )
    parser.add_argument(
        "--test-dir",
        required=True,
        help="Path to test dataset (must contain class folders like NORMAL and PNEUMONIA).",
    )
    parser.add_argument(
        "--model-path",
        default=str(DEFAULT_MODEL_PATH),
        help="Path to trained Keras model file (.h5).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Folder to save all generated report files.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size used during evaluation.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Threshold used when model output is a single sigmoid score.",
    )
    parser.add_argument(
        "--history-json",
        default=None,
        help="Optional path to training history JSON with keys: accuracy, val_accuracy, loss, val_loss.",
    )
    parser.add_argument(
        "--gradcam-image",
        default=None,
        help="Optional image path for Grad-CAM visualization.",
    )
    parser.add_argument(
        "--gradcam-layer",
        default=None,
        help="Optional convolution layer name for Grad-CAM (auto-detected if omitted).",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()

    # Example test-dir structure:
    # C:/path/to/test/
    #   NORMAL/
    #     xxx.jpeg
    #   PNEUMONIA/
    #     yyy.jpeg
    run_full_report(
        model_path=Path(args.model_path),
        test_dir=Path(args.test_dir),
        output_dir=Path(args.output_dir),
        batch_size=args.batch_size,
        threshold=args.threshold,
        history_json=args.history_json,
        gradcam_image=args.gradcam_image,
        gradcam_layer=args.gradcam_layer,
    )


# Run with your current test set:

# Open PowerShell in your project folder.
# Run:
# python.exe model_reporting_suite.py --test-dir "C:\Users\user\Downloads\archive\chest_xray\test"
# That already gives you:

# confusion matrix
# classification report
# ROC and AUC
# To also include Grad-CAM, add one test image path:
# python.exe model_reporting_suite.py --test-dir "C:\Users\user\Downloads\archive\chest_xray\test" --gradcam-image "C:\Users\user\Downloads\archive\chest_xray\test\PNEUMONIA\person1_virus_6.jpeg"

# To include training/validation accuracy and loss curves, add history JSON:
# python.exe model_reporting_suite.py --test-dir "C:\Users\user\Downloads\archive\chest_xray\test" --history-json "C:\path\to\history.json"


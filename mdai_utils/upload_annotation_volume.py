from pathlib import Path

import mdai
import numpy as np

from mdai_utils.dicoms_to_volume import metadata_dict_to_sop_instance_uids
from mdai_utils.upload_annotation_slice import read_data_image


def upload_data_annotation_volume(
    data_np: np.ndarray,
    sop_instance_uids: dict[int, str],
    mdai_client: mdai.Client,
    mdai_project_id: str,
    mdai_dataset_id: str,
    mdai_label_id: str,
) -> list:
    """
    Upload A 3D numpy array representing a segmentation mask. It requires that the DICOM image is already in md.ai.
    Args:
        data_np: A 3D numpy array representing a segmentation mask.
        sop_instance_uids: A dictionary mapping the slice index to the SOP Instance UID. See @dicoms_to_volume.dicoms_to_volume to get the mapping from the output metadata.
        mdai_client: An instance of the mdai.Client class.
        mdai_project_id: The md.ai project ID.
        mdai_dataset_id: The md.ai dataset ID.
        mdai_label_id: The md.ai label ID.
    Returns:
        A list of failed annotations.
    """

    if data_np.ndim != 3:
        raise ValueError("data_np must be a 3D numpy array.")

    mdai_annotations = []
    # Check that data_np and sop_instance_uids have the same number of slices
    len_data_np = len(data_np)
    len_sop_instance_uids = len(sop_instance_uids)
    if len_data_np != len_sop_instance_uids:
        raise ValueError(
            f"The number of slices in data_np ({len_data_np}) and sop_instance_uids ({len_sop_instance_uids}) must be the same."
        )
    # Iterate over the numpy slices (first index) and append the annotations to the list
    for i, data_slice in enumerate(data_np):
        # Get the SOP Instance UID
        sop_instance_uid = sop_instance_uids.get(i)
        # Upload the annotation
        annotation_dict = {
            "labelId": mdai_label_id,
            "SOPInstanceUID": sop_instance_uid,
            "data": mdai.common_utils.convert_mask_data(data_slice),
        }
        mdai_annotations.append(annotation_dict)

    failed_annotations = mdai_client.import_annotations(
        mdai_annotations, mdai_project_id, mdai_dataset_id
    )
    return failed_annotations


def upload_image_annotation_volume(
    segmentation_image_path: str,
    sop_instance_uids: dict[int, str],
    mdai_client: mdai.Client,
    mdai_project_id: str,
    mdai_dataset_id: str,
    mdai_label_id: str,
) -> list:
    """
    Upload a volume image containing a segmentation mask. It requires that the DICOM image is already in md.ai.
    The input image can be in any format supported by ITK.

    Args:
        segmentation_image_path: Path to the segmentation image. Any format compatible with ITK.
        sop_instance_uids: A dictionary mapping the slice index to the SOP Instance UID. See @dicoms_to_volume.dicoms_to_volume to get the mapping from the output metadata.
        mdai_client: An instance of the mdai.Client class.
        mdai_project_id: The md.ai project ID.
        mdai_dataset_id: The md.ai dataset ID.
        mdai_label_id: The md.ai label ID.
    Returns:
        A list of failed annotations.
    """
    data_np = read_data_image(segmentation_image_path)
    if data_np.ndim < 3:
        raise ValueError(
            f"Image has dimension {data_np.ndim}. Use aupload_image_annotation_slice instead of volume."
        )

    if data_np.ndim > 3:
        data_np = data_np.squeeze()
        if data_np.ndim != 3:
            raise ValueError("The input image seems to have more than 3 dimensions.")

    return upload_data_annotation_volume(
        data_np=data_np,
        sop_instance_uids=sop_instance_uids,
        mdai_client=mdai_client,
        mdai_project_id=mdai_project_id,
        mdai_dataset_id=mdai_dataset_id,
        mdai_label_id=mdai_label_id,
    )


def _get_parser():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i",
        "--input_annotation",
        type=str,
        required=True,
        help="Path to the segmentation image to upload.",
    )
    parser.add_argument(
        "-l",
        "--label_name",
        type=str,
        required=True,
        help="label name corresponding to the annotation.",
    )
    parser.add_argument(
        "--sop_instance_uids_file",
        type=str,
        required=True,
        help="json file generated by storing the metadata resulting from dicoms_to_volume.dicoms_to_volume",
    )
    parser.add_argument(
        "-p",
        "--parameters",
        type=str,
        default=None,
        help="""
Path to a json file containing the parameters for md.ai variables: mdai_project_id, mdai_dataset_id, mdai_label_ids, etc.
See example in tests/test_parameters.json.
""",
    )

    return parser


def main(
    input_annotation,
    label_name,
    sop_instance_uids_file,
    mdai_client,
    mdai_project_id,
    mdai_dataset_id,
    mdai_label_ids,
):
    sop_instance_uids_file_path = Path(sop_instance_uids_file)
    if not sop_instance_uids_file_path.exists():
        raise FileNotFoundError(
            f"The file {sop_instance_uids_file_path} does not exist."
        )
    with open(sop_instance_uids_file_path) as f:
        metadata_dict = json.load(f)

    sop_instance_uids = metadata_dict_to_sop_instance_uids(metadata_dict)

    mdai_label_id = mdai_label_ids[label_name]
    failed_annotations = upload_image_annotation_volume(
        segmentation_image_path=input_annotation,
        sop_instance_uids=sop_instance_uids,
        mdai_client=mdai_client,
        mdai_project_id=mdai_project_id,
        mdai_dataset_id=mdai_dataset_id,
        mdai_label_id=mdai_label_id,
    )
    return failed_annotations


if __name__ == "__main__":
    import json

    from mdai_utils.common import get_mdai_access_token

    parser = _get_parser()
    args = parser.parse_args()
    print(args)

    with open(args.parameters, "r") as f:
        parameters = json.load(f)

    mdai_project_id = parameters["mdai_project_id"]
    mdai_dataset_id = parameters["mdai_dataset_id"]
    mdai_label_ids = parameters["mdai_label_ids"]
    mdai_domain = parameters["mdai_domain"]

    input_annotation = args.input_annotation
    label_name = args.label_name
    mdai_label_id = mdai_label_ids[label_name]
    sop_instance_uids_file = args.sop_instance_uids_file

    token = get_mdai_access_token()
    mdai_client = mdai.Client(domain=mdai_domain, access_token=token)

    failed_annotations = main(
        input_annotation=input_annotation,
        label_name=label_name,
        sop_instance_uids_file=sop_instance_uids_file,
        mdai_client=mdai_client,
        mdai_project_id=mdai_project_id,
        mdai_dataset_id=mdai_dataset_id,
        mdai_label_ids=mdai_label_ids,
    )

    if len(failed_annotations) == 0:
        print("All annotations uploaded successfully.")
        exit(0)
    else:
        print(f"Failed annotations: {failed_annotations}")
        exit(1)